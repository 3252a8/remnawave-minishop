from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from http.cookies import SimpleCookie
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from asyncpg import Record

import httpx
import pytest

asyncpg = pytest.importorskip(
    "asyncpg",
    reason="full-stack QA database checks require asyncpg",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_URL = os.getenv("QA_FRONTEND_URL", "http://127.0.0.1:8082").rstrip("/")
API_BASE_URL = os.getenv("QA_API_BASE_URL", FRONTEND_URL).rstrip("/")
WEBHOOK_BASE_URL = os.getenv(
    "QA_WEBHOOK_BASE_URL",
    os.getenv("QA_BASE_URL", "http://127.0.0.1:8080"),
).rstrip("/")
REMNAWAVE_HEALTH_URL = os.getenv(
    "QA_REMNAWAVE_HEALTH_URL",
    "http://127.0.0.1:3001/health",
)
DB_DSN = os.getenv(
    "QA_DB_DSN",
    "postgresql://remnawave_minishop:remnawave_minishop@127.0.0.1:6768/remnawave_minishop",
)
QA_PAYMENT_SECRET = os.getenv("QA_PAYMENT_SECRET", "dev_qa_payment_secret_change_me")


@dataclass(frozen=True)
class WebAuthSession:
    user_id: int
    csrf_token: str
    cookie_header: str

    def headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Cookie": self.cookie_header,
            "X-CSRF-Token": self.csrf_token,
        }


@pytest.fixture(scope="session")
def client() -> Iterator[httpx.Client]:
    with httpx.Client(
        base_url=API_BASE_URL,
        timeout=httpx.Timeout(25.0, connect=5.0),
        follow_redirects=False,
    ) as http_client:
        _wait_for_http(http_client, "/api/bootstrap")
        yield http_client


def _wait_for_http(client: httpx.Client, path: str, *, timeout_seconds: int = 90) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: BaseException | None = None
    while time.monotonic() < deadline:
        try:
            response = client.get(path)
            if response.status_code == 200:
                return
            last_error = AssertionError(response.text)
        except (httpx.HTTPError, OSError) as exc:
            last_error = exc
        time.sleep(1)
    raise AssertionError(f"{path} did not become ready: {last_error}")


def _ok(response: httpx.Response) -> dict[str, Any]:
    assert response.status_code < 400, response.text
    data: dict[str, Any] = response.json()
    assert data.get("ok") is True, data
    return data


def _cookie_header_from(response: httpx.Response) -> str:
    cookie = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        cookie.load(header)
    values = {
        name: morsel.value
        for name, morsel in cookie.items()
        if name in {"rw_webapp_session", "rw_webapp_csrf"}
    }
    assert "rw_webapp_session" in values, response.headers
    assert "rw_webapp_csrf" in values, response.headers
    return "; ".join(f"{name}={value}" for name, value in values.items())


def login_email(client: httpx.Client, email: str) -> WebAuthSession:
    request_data = _ok(
        client.post(
            "/api/auth/email/request",
            json={"email": email, "language": "en"},
        )
    )
    code = str(request_data.get("email_code") or request_data.get("code") or "").strip()
    assert code and len(code) == 6, request_data

    verify_response = client.post(
        "/api/auth/email/verify",
        json={"email": email, "code": code},
    )
    verify_data = _ok(verify_response)
    csrf_token = str(verify_data.get("csrf_token") or "").strip()
    assert csrf_token, verify_data
    return WebAuthSession(
        user_id=int(verify_data["user_id"]),
        csrf_token=csrf_token,
        cookie_header=_cookie_header_from(verify_response),
    )


def _signed_json(payload: dict[str, Any]) -> tuple[bytes, str]:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(
        QA_PAYMENT_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return body, signature


async def _fetch_payment_amount_and_currency(payment_id: int) -> Record:
    connection = await asyncpg.connect(DB_DSN)
    try:
        payment = await connection.fetchrow(
            """
            select amount, currency
            from payments
            where payment_id = $1
            """,
            payment_id,
        )
        assert payment is not None
        return payment
    finally:
        await connection.close()


async def _fetch_payment_and_latest_subscription(
    payment_id: int,
    user_id: int,
) -> tuple[Record | None, Record | None]:
    connection = await asyncpg.connect(DB_DSN)
    try:
        payment = await connection.fetchrow(
            """
            select payment_id, user_id, provider, provider_payment_id, status, amount, currency
            from payments
            where payment_id = $1
            """,
            payment_id,
        )
        subscription = await connection.fetchrow(
            """
            select subscription_id, user_id, provider, duration_months, is_active, tariff_key,
                   end_date
            from subscriptions
            where user_id = $1
            order by end_date desc nulls last, subscription_id desc
            limit 1
            """,
            user_id,
        )
        assert payment is not None
        assert subscription is not None
        return payment, subscription
    finally:
        await connection.close()


def _find_admin_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    sections: list[dict[str, Any]] = payload.get("sections", [])
    for section in sections:
        fields: list[dict[str, Any]] = section.get("fields", [])
        for field in fields:
            if field.get("key") == key:
                return field
    raise AssertionError(f"admin settings field {key!r} was not found")


def test_email_auth_session_and_csrf(client: httpx.Client) -> None:
    email = f"qa-auth-{uuid.uuid4().hex}@example.com"
    session = login_email(client, email)

    me = _ok(client.get("/api/me", headers=session.headers()))
    assert me["user"]["id"] == session.user_id
    assert me["user"]["email"] == email

    language = _ok(
        client.post(
            "/api/account/language",
            headers=session.headers(),
            json={"language": "en"},
        )
    )
    assert language["language"] == "en"


def test_qa_payment_webhook_activates_subscription(client: httpx.Client) -> None:
    session = login_email(client, "runes.expired@example.com")

    payment_data = _ok(
        client.post(
            "/api/payments",
            headers=session.headers(),
            json={
                "method": "qa",
                "months": 1,
                "tariff_key": "standard",
                "sale_mode": "subscription",
            },
        )
    )
    payment_id = int(payment_data["payment_id"])
    assert payment_data["payment_url"]
    payment_record = asyncio.run(_fetch_payment_amount_and_currency(payment_id))

    body, signature = _signed_json(
        {
            "payment_id": payment_id,
            "provider_payment_id": f"qa:{payment_id}:webhook",
            "status": "succeeded",
            "amount": float(payment_record["amount"]),
            "currency": str(payment_record["currency"]),
        }
    )
    webhook_data = _ok(
        httpx.post(
            f"{WEBHOOK_BASE_URL}/webhook/qa-payment",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-QA-Payment-Signature": signature,
            },
        )
    )
    assert webhook_data["status"] == "succeeded"

    status = _ok(client.get(f"/api/payments/{payment_id}", headers=session.headers()))
    assert status["paid"] is True
    assert status["status"] == "succeeded"

    payment, subscription = asyncio.run(
        _fetch_payment_and_latest_subscription(payment_id, session.user_id)
    )
    assert payment is not None
    assert subscription is not None
    assert payment["provider"] == "qa"
    assert payment["status"] == "succeeded"
    assert subscription["provider"] == "qa"
    assert subscription["duration_months"] == 1
    assert subscription["is_active"] is True


def test_admin_settings_save_roundtrip(client: httpx.Client) -> None:
    session = login_email(client, "runes.admin@example.com")
    admin = _ok(client.get("/api/admin/me", headers=session.headers()))
    assert session.user_id in admin["admin_ids"]

    value = f"https://status.qa.example.test/{uuid.uuid4().hex}"
    try:
        saved = _ok(
            client.patch(
                "/api/admin/settings",
                headers=session.headers(),
                json={"updates": {"SERVER_STATUS_URL": value}, "deletes": []},
            )
        )
        assert saved["applied"] >= 1

        settings_payload = _ok(client.get("/api/admin/settings", headers=session.headers()))
        field = _find_admin_field(settings_payload, "SERVER_STATUS_URL")
        assert field["value"] == value
        assert field["overridden"] is True
    finally:
        client.patch(
            "/api/admin/settings",
            headers=session.headers(),
            json={"updates": {}, "deletes": ["SERVER_STATUS_URL"]},
        )


def test_remnawave_versions_are_pinned_and_healthy(client: httpx.Client) -> None:
    lock_path = REPO_ROOT / "deploy" / "dev" / "remnawave-versions.lock.json"
    env_example = (REPO_ROOT / "deploy" / "dev" / "remnawave-dev.env.example").read_text(
        encoding="utf-8"
    )
    lock = json.loads(lock_path.read_text(encoding="utf-8"))

    assert f"REMNAWAVE_DEV_VERSION={lock['remnawave_panel']}" in env_example
    assert f"REMNAWAVE_NODE_VERSION={lock['remnawave_node']}" in env_example
    assert f"REMNAWAVE_SUBSCRIPTION_PAGE_VERSION={lock['subscription_page']}" in env_example

    frontend = httpx.get(FRONTEND_URL, timeout=10.0)
    assert frontend.status_code < 500, frontend.text[:500]

    remnawave = httpx.get(REMNAWAVE_HEALTH_URL, timeout=10.0)
    assert remnawave.status_code == 200, remnawave.text
