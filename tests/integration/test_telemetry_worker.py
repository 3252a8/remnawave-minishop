"""Telemetry beacon: payload shape, anonymity and bucketing.

These tests never touch the network or a database: ``_build_payload`` is given
a ``None`` session (the user-count lookup degrades to 0) and a fixed install id,
so we can assert the PostHog-shaped envelope and that no secrets leak.
"""

import asyncio
import json

import pytest

from bot.services.telemetry_worker import HEARTBEAT_EVENT, TelemetryWorker, _bucket_users
from config.settings import Settings


@pytest.fixture
def settings(monkeypatch) -> Settings:
    # Provide the minimal required env so Settings() validates without a .env,
    # keeping the test self-contained in CI.
    monkeypatch.setenv("BOT_TOKEN", "1234567890:AA_secret_bot_token_value")
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "Sup3rSecretDbPassw0rd")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("ADMIN_IDS", "1")
    return Settings()


def test_bucket_users_boundaries():
    assert _bucket_users(0) == "0"
    assert _bucket_users(1) == "1-10"
    assert _bucket_users(10) == "1-10"
    assert _bucket_users(11) == "11-50"
    assert _bucket_users(50) == "11-50"
    assert _bucket_users(200) == "51-200"
    assert _bucket_users(1000) == "201-1000"
    assert _bucket_users(5000) == "1001-5000"
    assert _bucket_users(5001) == "5000+"
    assert _bucket_users(99999) == "5000+"


def test_build_payload_shape(settings):
    worker = TelemetryWorker(settings, None)
    payload = asyncio.run(worker._build_payload(None, "install-123"))

    assert payload["event"] == HEARTBEAT_EVENT
    assert payload["distinct_id"] == "install-123"
    assert payload["api_key"] == settings.TELEMETRY_API_KEY.strip()

    props = payload["properties"]
    for key in (
        "app_version",
        "app_version_tag",
        "build_provenance",
        "image_modified",
        "os",
        "arch",
        "python_version",
        "locale",
        "users_bucket",
        "payment_providers",
        "webapp_enabled",
        "panel_configured",
    ):
        assert key in props, f"missing property: {key}"

    assert isinstance(props["payment_providers"], list)
    assert props["build_provenance"] in {"official", "custom", "unknown"}
    assert isinstance(props["image_modified"], bool)
    # No DB session -> user count degrades to the smallest bucket.
    assert props["users_bucket"] == "0"
    # Person properties mirror the event properties so PostHog breakdowns work.
    assert props["$set"]["app_version"] == props["app_version"]
    assert props["$set"]["build_provenance"] == props["build_provenance"]
    assert props["$set"]["image_modified"] == props["image_modified"]
    assert props["$lib"] == "remnawave-minishop"


def test_payload_marks_official_images_not_modified(settings, monkeypatch):
    monkeypatch.setattr(
        "bot.services.telemetry_worker.resolve_build_provenance",
        lambda: "official",
    )
    monkeypatch.setattr("bot.services.telemetry_worker.resolve_image_modified", lambda: False)

    worker = TelemetryWorker(settings, None)
    payload = asyncio.run(worker._build_payload(None, "install-123"))
    props = payload["properties"]

    assert props["build_provenance"] == "official"
    assert props["image_modified"] is False


def test_payload_marks_custom_images_modified(settings, monkeypatch):
    monkeypatch.setattr("bot.services.telemetry_worker.resolve_build_provenance", lambda: "custom")
    monkeypatch.setattr("bot.services.telemetry_worker.resolve_image_modified", lambda: True)

    worker = TelemetryWorker(settings, None)
    payload = asyncio.run(worker._build_payload(None, "install-123"))
    props = payload["properties"]

    assert props["build_provenance"] == "custom"
    assert props["image_modified"] is True


def test_payload_contains_no_secrets_or_pii(settings):
    worker = TelemetryWorker(settings, None)
    payload = asyncio.run(worker._build_payload(None, "install-123"))
    blob = json.dumps(payload)

    # The bot token and DB password must never appear in the beacon.
    assert settings.BOT_TOKEN not in blob
    assert settings.POSTGRES_PASSWORD not in blob


def test_delivery_disabled_without_endpoint_or_key(settings, monkeypatch):
    worker = TelemetryWorker(settings, None)
    assert worker._delivery_configured() is True

    monkeypatch.setattr(settings, "TELEMETRY_API_KEY", "", raising=False)
    assert worker._delivery_configured() is False

    monkeypatch.setattr(settings, "TELEMETRY_API_KEY", "phc_x", raising=False)
    monkeypatch.setattr(settings, "TELEMETRY_ENDPOINT", "", raising=False)
    assert worker._delivery_configured() is False
