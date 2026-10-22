"""Direct unit tests for the shared link-payment engine.

These pin the orchestration independently of any concrete provider: a synthetic
descriptor + fakes drive the three engine flows, and the heavy shared
collaborators are patched on the engine module namespace.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web

from bot.payment_providers.shared import callbacks as shared_callbacks
from bot.payment_providers.shared import link_flow
from bot.payment_providers.shared import webapp as shared_webapp
from bot.payment_providers.shared.link_flow import (
    CreatePaymentRequest,
    LinkPaymentDescriptor,
    run_callback_payment,
    run_reuse_webapp_payment,
    run_webapp_payment,
)


class _FakeService:
    def __init__(self, configured: bool = True):
        self._configured = configured
        self.subscription_service = object()

    @property
    def configured(self) -> bool:
        return self._configured


def _descriptor(**overrides):
    base = {
        "spec": SimpleNamespace(
            is_available_to_user=lambda *a, **k: True,
            callback_prefix="pay_fake",
        ),
        "provider_key": "fake",
        "pending_status": "pending_fake",
        "display_name": "Fake",
        "log_prefix": "fake",
        "service_app_key": "fake_service",
        "service_type": _FakeService,
        "create": AsyncMock(return_value=(True, {"url": "https://pay/x", "id": "pid-1"})),
        "reuse": AsyncMock(return_value=None),
        "extract_url": lambda r: r.get("url"),
        "extract_provider_id": lambda r: r.get("id"),
    }
    base.update(overrides)
    return LinkPaymentDescriptor(**base)


def _patch_common(monkeypatch):
    """Patch the shared collaborators the engine calls on its own namespace."""
    monkeypatch.setattr(link_flow, "default_currency_key_for_settings", lambda s: "RUB")
    monkeypatch.setattr(link_flow, "default_payment_currency_code_for_settings", lambda s: "RUB")
    monkeypatch.setattr(link_flow, "describe_payment", lambda *a, **k: "desc")
    monkeypatch.setattr(link_flow, "build_payment_record_payload", lambda **k: {"payload": True})
    monkeypatch.setattr(
        link_flow,
        "payment_record_amounts",
        lambda **k: SimpleNamespace(
            months=1, purchased_gb=None, purchased_hwid_devices=None, tariff_key=None
        ),
    )
    parts = SimpleNamespace(
        price=100.0,
        months=1,
        sale_mode="subscription",
        entitlement_context_snapshot="entitlement-snapshot",
    )
    monkeypatch.setattr(link_flow, "parse_payment_callback", lambda data: parts)

    async def _quote(**kwargs):
        assert kwargs["settings"] is not None
        return parts, None

    monkeypatch.setattr(link_flow, "quote_hwid_callback_parts", _quote)
    for name in (
        "notify_service_unavailable",
        "notify_callback_parse_error",
        "notify_payment_record_failure",
        "render_link_or_fail",
        "render_payment_link",
    ):
        monkeypatch.setattr(link_flow, name, AsyncMock())
    return parts


def _callback():
    return SimpleNamespace(
        message=object(),
        from_user=SimpleNamespace(id=123),
        data="pay_fake:sub:1",
    )


def _settings():
    return SimpleNamespace(DEFAULT_LANGUAGE="en", DEFAULT_CURRENCY_SYMBOL="RUB")


def _session():
    return SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())


def test_callback_create_path_calls_create_and_renders(monkeypatch):
    _patch_common(monkeypatch)
    payment = SimpleNamespace(payment_id=42, status="pending_fake")
    fake_dal = SimpleNamespace(
        find_recent_pending_provider_payment=AsyncMock(return_value=None),
        create_payment_record=AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(link_flow, "payment_dal", fake_dal)

    desc = _descriptor()
    service = _FakeService()
    asyncio.run(
        run_callback_payment(
            desc, _callback(), _settings(), {"i18n_instance": object()}, service, _session()
        )
    )

    # create adapter received the right request, derived from the parsed parts
    desc.create.assert_awaited_once()
    called_service, req = desc.create.await_args.args
    assert called_service is service
    assert isinstance(req, CreatePaymentRequest)
    assert req.payment is payment and req.user_id == 123 and req.amount == 100.0
    assert req.months == 1 and req.sale_mode == "subscription"
    # the link was rendered with the descriptor's extracted url/id
    link_flow.render_link_or_fail.assert_awaited_once()
    kwargs = link_flow.render_link_or_fail.await_args.kwargs
    assert kwargs["payment_url"] == "https://pay/x"
    assert kwargs["provider_payment_id"] == "pid-1"
    assert kwargs["lead_text"] is None
    assert kwargs["log_prefix"] == "fake"


def test_callback_reuse_hit_short_circuits(monkeypatch):
    _patch_common(monkeypatch)
    existing = SimpleNamespace(payment_id=7)
    fake_dal = SimpleNamespace(
        find_recent_pending_provider_payment=AsyncMock(return_value=existing),
        create_payment_record=AsyncMock(),
    )
    monkeypatch.setattr(link_flow, "payment_dal", fake_dal)

    desc = _descriptor(reuse=AsyncMock(return_value="https://pay/reused"))
    asyncio.run(
        run_callback_payment(
            desc, _callback(), _settings(), {"i18n_instance": object()}, _FakeService(), _session()
        )
    )

    desc.reuse.assert_awaited_once()
    link_flow.render_payment_link.assert_awaited_once()
    # no new record created, no create() call on a reuse hit
    fake_dal.create_payment_record.assert_not_awaited()
    desc.create.assert_not_awaited()


def test_callback_reuse_rolls_back_before_provider_call(monkeypatch):
    _patch_common(monkeypatch)
    existing = SimpleNamespace(payment_id=7, provider_payment_id="provider-7")
    events: list[object] = []
    fake_dal = SimpleNamespace(
        find_recent_pending_provider_payment=AsyncMock(return_value=existing),
        create_payment_record=AsyncMock(),
    )
    monkeypatch.setattr(link_flow, "payment_dal", fake_dal)

    async def reuse(_service, payment):
        events.append(("reuse", payment))
        return "https://pay/reused"

    session = _session()
    session.rollback = AsyncMock(side_effect=lambda: events.append("rollback"))
    desc = _descriptor(reuse=AsyncMock(side_effect=reuse))

    asyncio.run(
        run_callback_payment(
            desc, _callback(), _settings(), {"i18n_instance": object()}, _FakeService(), session
        )
    )

    assert events[0] == "rollback"
    assert isinstance(events[1], tuple)
    reused_payment = events[1][1]
    assert reused_payment is not existing
    assert reused_payment.payment_id == 7
    assert reused_payment.provider_payment_id == "provider-7"
    fake_dal.create_payment_record.assert_not_awaited()


def test_callback_reuse_lookup_uses_descriptor_ttl(monkeypatch):
    _patch_common(monkeypatch)
    fake_dal = SimpleNamespace(
        find_recent_pending_provider_payment=AsyncMock(return_value=None),
        create_payment_record=AsyncMock(return_value=SimpleNamespace(payment_id=42)),
    )
    monkeypatch.setattr(link_flow, "payment_dal", fake_dal)

    desc = _descriptor(callback_reuse_since_minutes=lambda service, context: 17)
    asyncio.run(
        run_callback_payment(
            desc, _callback(), _settings(), {"i18n_instance": object()}, _FakeService(), _session()
        )
    )

    reuse_kwargs = fake_dal.find_recent_pending_provider_payment.await_args.kwargs
    assert reuse_kwargs["since_minutes"] == 17
    assert reuse_kwargs["entitlement_context_snapshot"] == "entitlement-snapshot"


def test_callback_can_disable_reuse_lookup(monkeypatch):
    _patch_common(monkeypatch)
    fake_dal = SimpleNamespace(
        find_recent_pending_provider_payment=AsyncMock(),
        create_payment_record=AsyncMock(return_value=SimpleNamespace(payment_id=42)),
    )
    monkeypatch.setattr(link_flow, "payment_dal", fake_dal)

    desc = _descriptor(callback_reuse_enabled=False)
    asyncio.run(
        run_callback_payment(
            desc, _callback(), _settings(), {"i18n_instance": object()}, _FakeService(), _session()
        )
    )

    fake_dal.find_recent_pending_provider_payment.assert_not_awaited()
    fake_dal.create_payment_record.assert_awaited_once()


def test_callback_payment_guard_blocks_before_record(monkeypatch):
    _patch_common(monkeypatch)
    fake_dal = SimpleNamespace(
        find_recent_pending_provider_payment=AsyncMock(),
        create_payment_record=AsyncMock(),
    )
    monkeypatch.setattr(link_flow, "payment_dal", fake_dal)

    desc = _descriptor(
        callback_payment_allowed=lambda service, settings, user_id, amount, currency: False
    )
    asyncio.run(
        run_callback_payment(
            desc, _callback(), _settings(), {"i18n_instance": object()}, _FakeService(), _session()
        )
    )

    link_flow.notify_service_unavailable.assert_awaited_once()
    fake_dal.create_payment_record.assert_not_awaited()
    desc.create.assert_not_awaited()


def test_callback_lead_text_is_passed_to_renderer(monkeypatch):
    _patch_common(monkeypatch)
    payment = SimpleNamespace(payment_id=42, status="pending_fake")
    fake_dal = SimpleNamespace(
        find_recent_pending_provider_payment=AsyncMock(return_value=None),
        create_payment_record=AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(link_flow, "payment_dal", fake_dal)

    desc = _descriptor(callback_lead_text=lambda req, response, translator: "Order #1")
    asyncio.run(
        run_callback_payment(
            desc, _callback(), _settings(), {"i18n_instance": object()}, _FakeService(), _session()
        )
    )

    kwargs = link_flow.render_link_or_fail.await_args.kwargs
    assert kwargs["lead_text"] == "Order #1"


def test_callback_before_create_hook_runs_after_record_creation(monkeypatch):
    _patch_common(monkeypatch)
    payment = SimpleNamespace(payment_id=42, status="pending_fake")
    events: list[str] = []
    fake_dal = SimpleNamespace(
        find_recent_pending_provider_payment=AsyncMock(return_value=None),
        create_payment_record=AsyncMock(
            side_effect=lambda session, payload: events.append("record") or payment
        ),
    )
    monkeypatch.setattr(link_flow, "payment_dal", fake_dal)

    async def before_create(callback):
        assert callback is not None
        events.append("answer")

    async def create(service, request):
        events.append("create")
        return True, {"url": "https://pay/x", "id": "pid-1"}

    desc = _descriptor(
        callback_before_create=before_create,
        create=AsyncMock(side_effect=create),
    )
    asyncio.run(
        run_callback_payment(
            desc, _callback(), _settings(), {"i18n_instance": object()}, _FakeService(), _session()
        )
    )

    assert events == ["record", "answer", "create"]


def test_callback_context_is_passed_to_create_request(monkeypatch):
    _patch_common(monkeypatch)
    payment = SimpleNamespace(payment_id=42, status="pending_fake")
    fake_dal = SimpleNamespace(
        find_recent_pending_provider_payment=AsyncMock(return_value=None),
        create_payment_record=AsyncMock(return_value=payment),
    )
    monkeypatch.setattr(link_flow, "payment_dal", fake_dal)

    desc = _descriptor(callback_context=lambda callback, parts, service: {"variant": "sbp"})
    asyncio.run(
        run_callback_payment(
            desc, _callback(), _settings(), {"i18n_instance": object()}, _FakeService(), _session()
        )
    )

    _service, request = desc.create.await_args.args
    assert request.provider_context == {"variant": "sbp"}


def test_callback_reuse_validator_skips_stale_payment(monkeypatch):
    _patch_common(monkeypatch)
    existing = SimpleNamespace(payment_id=7)
    created = SimpleNamespace(payment_id=42, status="pending_fake")
    fake_dal = SimpleNamespace(
        find_recent_pending_provider_payment=AsyncMock(return_value=existing),
        create_payment_record=AsyncMock(return_value=created),
    )
    monkeypatch.setattr(link_flow, "payment_dal", fake_dal)

    desc = _descriptor(
        callback_context=lambda callback, parts, service: {"variant": "sbp"},
        reuse=AsyncMock(return_value="https://pay/reused"),
        reuse_payment_allowed=lambda payment, context: False,
    )
    asyncio.run(
        run_callback_payment(
            desc, _callback(), _settings(), {"i18n_instance": object()}, _FakeService(), _session()
        )
    )

    desc.reuse.assert_not_awaited()
    fake_dal.create_payment_record.assert_awaited_once()
    desc.create.assert_awaited_once()


def test_callback_unconfigured_service_notifies(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(link_flow, "payment_dal", SimpleNamespace())
    desc = _descriptor()
    asyncio.run(
        run_callback_payment(
            desc,
            _callback(),
            _settings(),
            {"i18n_instance": object()},
            _FakeService(configured=False),
            _session(),
        )
    )
    link_flow.notify_service_unavailable.assert_awaited_once()
    desc.create.assert_not_awaited()


def _webapp_ctx(service, configured_settings=True):
    app = {"settings": _settings(), "fake_service": service}
    return SimpleNamespace(
        request=SimpleNamespace(app=app),
        session=_session(),
        user_id=555,
        price=100.0,
        currency="RUB",
        description="webapp desc",
        months=1,
        sale_mode="subscription",
    )


def test_webapp_payment_success_finalizes(monkeypatch):
    payment = SimpleNamespace(payment_id=99, status="pending_fake")
    monkeypatch.setattr(link_flow, "create_webapp_payment_record", AsyncMock(return_value=payment))
    monkeypatch.setattr(link_flow, "finalize_webapp_link_payment", AsyncMock(return_value="OK"))

    desc = _descriptor()
    service = _FakeService()
    result = asyncio.run(run_webapp_payment(desc, _webapp_ctx(service)))

    assert result == "OK"
    desc.create.assert_awaited_once()
    _svc, req = desc.create.await_args.args
    assert req.user_id == 555 and req.description == "webapp desc"
    assert req.months == 1 and req.sale_mode == "subscription"
    fin = link_flow.finalize_webapp_link_payment.await_args.kwargs
    assert fin["payment_url"] == "https://pay/x"
    assert fin["provider_payment_id"] == "pid-1"
    assert fin["log_prefix"] == "Fake"


def test_webapp_payment_retires_older_provider_links_after_success(monkeypatch):
    payment = SimpleNamespace(payment_id=99, status="pending_fake")
    service = _FakeService()
    service.cancel_pending_bill = AsyncMock()
    response = web.json_response({"ok": True})
    supersede = AsyncMock()
    monkeypatch.setattr(link_flow, "create_webapp_payment_record", AsyncMock(return_value=payment))
    monkeypatch.setattr(
        link_flow,
        "finalize_webapp_link_payment",
        AsyncMock(return_value=response),
    )
    monkeypatch.setattr(link_flow, "supersede_earlier_pending_hosted_checkouts", supersede)

    desc = _descriptor()
    ctx = _webapp_ctx(service)
    result = asyncio.run(run_webapp_payment(desc, ctx))

    assert result is response
    args = supersede.await_args
    assert args is not None
    assert args.args[0] is ctx.session
    assert args.args[1].payment_id == 99
    assert args.args[2] is service
    assert args.kwargs == {"pending_status": "pending_fake"}


def test_webapp_payment_persists_descriptor_ttl_when_provider_omits_expiry(monkeypatch):
    payment = SimpleNamespace(payment_id=99, status="pending_fake")
    monkeypatch.setattr(link_flow, "create_webapp_payment_record", AsyncMock(return_value=payment))
    monkeypatch.setattr(link_flow, "finalize_webapp_link_payment", AsyncMock(return_value="OK"))
    service = _FakeService()
    started_at = datetime.now(UTC)
    desc = _descriptor(checkout_ttl_seconds=lambda _service, _request: 600)

    result = asyncio.run(run_webapp_payment(desc, _webapp_ctx(service)))

    assert result == "OK"
    expires_at = link_flow.finalize_webapp_link_payment.await_args.kwargs["checkout_expires_at"]
    assert started_at + timedelta(seconds=600) <= expires_at
    assert expires_at <= datetime.now(UTC) + timedelta(seconds=600)


def test_webapp_payment_unconfigured_returns_unavailable(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(link_flow, "payment_unavailable", lambda: sentinel)
    desc = _descriptor()
    result = asyncio.run(run_webapp_payment(desc, _webapp_ctx(_FakeService(configured=False))))
    assert result is sentinel


def test_webapp_link_is_not_exposed_when_provider_correlation_cannot_be_persisted(
    monkeypatch,
) -> None:
    session = _session()
    payment = SimpleNamespace(
        payment_id=99,
        user_id=555,
        status="pending_fake",
    )
    persist = AsyncMock(side_effect=RuntimeError("database unavailable"))
    mark_failed = AsyncMock()
    monkeypatch.setattr(
        shared_webapp.payment_dal,
        "update_provider_payment_and_status",
        persist,
    )
    monkeypatch.setattr(
        shared_webapp,
        "mark_payment_failed_creation",
        mark_failed,
    )

    response = asyncio.run(
        shared_webapp.finalize_webapp_link_payment(
            session=session,
            payment=payment,
            api_success=True,
            payment_url="https://pay/x",
            provider_payment_id="shop-order-uuid",
            provider_response={"uuid": "shop-order-uuid"},
            log_prefix="Tribute Shop",
        )
    )

    assert response.status == 502
    assert response.body
    assert b'"error": "payment_failed"' in response.body
    persist.assert_awaited_once()
    session.rollback.assert_awaited_once()
    mark_failed.assert_awaited_once_with(
        session,
        payment.payment_id,
        failure_kind="provider_correlation_persist_failed",
        failure_http_status=None,
        failure_provider_code=None,
    )


def test_webapp_link_is_not_exposed_without_provider_correlation(
    monkeypatch,
) -> None:
    session = _session()
    payment = SimpleNamespace(
        payment_id=100,
        user_id=555,
        status="pending_fake",
    )
    persist = AsyncMock()
    mark_failed = AsyncMock()
    monkeypatch.setattr(
        shared_webapp.payment_dal,
        "update_provider_payment_and_status",
        persist,
    )
    monkeypatch.setattr(
        shared_webapp,
        "mark_payment_failed_creation",
        mark_failed,
    )

    response = asyncio.run(
        shared_webapp.finalize_webapp_link_payment(
            session=session,
            payment=payment,
            api_success=True,
            payment_url="https://pay/x",
            provider_payment_id=None,
            provider_response={"url": "https://pay/x"},
            log_prefix="Fake",
        )
    )

    assert response.status == 502
    persist.assert_not_awaited()
    mark_failed.assert_awaited_once_with(
        session,
        payment.payment_id,
        failure_kind="provider_response_invalid",
        failure_http_status=None,
        failure_provider_code=None,
    )


def test_webapp_gateway_outage_returns_typed_fallback_error(monkeypatch) -> None:
    mark_failed = AsyncMock()
    monkeypatch.setattr(shared_webapp, "mark_payment_failed_creation", mark_failed)
    response = asyncio.run(
        shared_webapp.finalize_webapp_link_payment(
            session=_session(),
            payment=SimpleNamespace(payment_id=102, user_id=555),
            api_success=False,
            payment_url=None,
            provider_response={"status": 503, "message": "invalid_json"},
            log_prefix="Fake",
        )
    )
    assert response.status == 502
    assert response.body and b'"error": "payment_provider_unavailable"' in response.body
    mark_failed.assert_awaited_once()
    assert mark_failed.await_args is not None
    assert mark_failed.await_args.kwargs["suppress_failure_notification"] is True


def test_callback_gateway_outage_renders_alternatives_without_creating_payment(monkeypatch) -> None:
    parts = shared_callbacks.PaymentCallbackParts(months=1, price=100, sale_mode="subscription")
    settings = _settings()
    keyboard = object()
    fallback = AsyncMock(return_value=None)
    mark_failed = AsyncMock()
    monkeypatch.setattr(shared_callbacks, "safe_mark_failed_creation", mark_failed)
    monkeypatch.setattr(shared_callbacks, "safe_callback_answer", AsyncMock())
    monkeypatch.setattr(shared_callbacks, "edit_or_answer", fallback)
    monkeypatch.setattr(
        shared_callbacks, "payment_fallback_keyboard", lambda *_args, **_kwargs: (keyboard, True)
    )
    asyncio.run(
        shared_callbacks.render_link_or_fail(
            _callback(),
            translator=lambda key, **_kwargs: key,
            current_lang="en",
            i18n=None,
            parts=parts,
            session=_session(),
            payment=SimpleNamespace(payment_id=103, user_id=123),
            api_success=False,
            payment_url=None,
            provider_response={"status": 503},
            log_prefix="Fake",
            settings=settings,
        )
    )
    fallback.assert_awaited_once()
    assert fallback.await_args is not None
    assert fallback.await_args.args[1] == "payment_provider_unavailable_alternative"
    assert fallback.await_args.kwargs["reply_markup"] is keyboard
    mark_failed.assert_awaited_once()
    assert mark_failed.await_args is not None
    assert (
        mark_failed.await_args.kwargs["failure_metadata"]["suppress_failure_notification"] is True
    )


def test_webapp_link_is_not_exposed_after_unsuccessful_provider_response(
    monkeypatch,
) -> None:
    session = _session()
    payment = SimpleNamespace(
        payment_id=101,
        user_id=555,
        status="pending_fake",
    )
    persist = AsyncMock()
    mark_failed = AsyncMock()
    monkeypatch.setattr(
        shared_webapp.payment_dal,
        "update_provider_payment_and_status",
        persist,
    )
    monkeypatch.setattr(
        shared_webapp,
        "mark_payment_failed_creation",
        mark_failed,
    )

    response = asyncio.run(
        shared_webapp.finalize_webapp_link_payment(
            session=session,
            payment=payment,
            api_success=False,
            payment_url="https://pay/x",
            provider_payment_id="unexpected-id",
            provider_response={"error": "rejected", "url": "https://pay/x"},
            log_prefix="Fake",
        )
    )

    assert response.status == 502
    persist.assert_not_awaited()
    mark_failed.assert_awaited_once_with(
        session,
        payment.payment_id,
        failure_kind="provider_request_rejected",
        failure_http_status=None,
        failure_provider_code="rejected",
    )


def test_callback_link_is_not_rendered_when_provider_correlation_cannot_be_persisted(
    monkeypatch,
) -> None:
    session = _session()
    payment = SimpleNamespace(
        payment_id=42,
        user_id=123,
        status="pending_fake",
    )
    store = AsyncMock(return_value=False)
    render = AsyncMock()
    mark_failed = AsyncMock()
    notify_failed = AsyncMock()
    monkeypatch.setattr(
        shared_callbacks,
        "safe_store_provider_payment_id",
        store,
    )
    monkeypatch.setattr(shared_callbacks, "render_payment_link", render)
    monkeypatch.setattr(
        shared_callbacks,
        "safe_mark_failed_creation",
        mark_failed,
    )
    monkeypatch.setattr(
        shared_callbacks,
        "notify_payment_gateway_failure",
        notify_failed,
    )

    asyncio.run(
        shared_callbacks.render_link_or_fail(
            _callback(),
            translator=lambda key, **kwargs: key,
            current_lang="en",
            i18n=SimpleNamespace(),
            parts=SimpleNamespace(
                price=100.0,
                months=1,
                sale_mode="subscription",
            ),
            session=session,
            payment=payment,
            api_success=True,
            payment_url="https://pay/x",
            provider_payment_id="shop-order-uuid",
            provider_response={"uuid": "shop-order-uuid"},
            log_prefix="tribute",
        )
    )

    store.assert_awaited_once()
    render.assert_not_awaited()
    mark_failed.assert_awaited_once_with(
        session,
        payment,
        log_prefix="tribute",
        failure_metadata={
            "failure_kind": "provider_correlation_persist_failed",
            "failure_http_status": None,
            "failure_provider_code": None,
        },
    )
    notify_failed.assert_awaited_once()


def test_callback_link_is_not_rendered_without_provider_correlation(
    monkeypatch,
) -> None:
    session = _session()
    payment = SimpleNamespace(
        payment_id=43,
        user_id=123,
        status="pending_fake",
    )
    store = AsyncMock()
    render = AsyncMock()
    mark_failed = AsyncMock()
    notify_failed = AsyncMock()
    monkeypatch.setattr(
        shared_callbacks,
        "safe_store_provider_payment_id",
        store,
    )
    monkeypatch.setattr(shared_callbacks, "render_payment_link", render)
    monkeypatch.setattr(
        shared_callbacks,
        "safe_mark_failed_creation",
        mark_failed,
    )
    monkeypatch.setattr(
        shared_callbacks,
        "notify_payment_gateway_failure",
        notify_failed,
    )

    asyncio.run(
        shared_callbacks.render_link_or_fail(
            _callback(),
            translator=lambda key, **kwargs: key,
            current_lang="en",
            i18n=SimpleNamespace(),
            parts=SimpleNamespace(
                price=100.0,
                months=1,
                sale_mode="subscription",
            ),
            session=session,
            payment=payment,
            api_success=True,
            payment_url="https://pay/x",
            provider_payment_id=None,
            provider_response={"url": "https://pay/x"},
            log_prefix="fake",
        )
    )

    store.assert_not_awaited()
    render.assert_not_awaited()
    mark_failed.assert_awaited_once_with(
        session,
        payment,
        log_prefix="fake",
        failure_metadata={
            "failure_kind": "provider_response_invalid",
            "failure_http_status": None,
            "failure_provider_code": None,
        },
    )
    notify_failed.assert_awaited_once()


def test_webapp_currency_resolver_receives_service(monkeypatch):
    payment = SimpleNamespace(payment_id=99, status="pending_fake")
    monkeypatch.setattr(link_flow, "create_webapp_payment_record", AsyncMock(return_value=payment))
    monkeypatch.setattr(link_flow, "finalize_webapp_link_payment", AsyncMock(return_value="OK"))

    service = _FakeService()
    desc = _descriptor(webapp_currency=lambda ctx, settings, resolved_service: "USD")
    asyncio.run(run_webapp_payment(desc, _webapp_ctx(service)))

    _svc, req = desc.create.await_args.args
    assert _svc is service
    assert req.currency == "USD"


def test_reuse_webapp_delegates_to_descriptor(monkeypatch):
    desc = _descriptor(reuse=AsyncMock(return_value="https://pay/reused"))
    service = _FakeService()
    payment = SimpleNamespace(payment_id=1)
    url = asyncio.run(run_reuse_webapp_payment(desc, _webapp_ctx(service), payment))
    assert url == "https://pay/reused"
    desc.reuse.assert_awaited_once_with(service, payment)


def test_reuse_webapp_unconfigured_returns_none():
    desc = _descriptor(reuse=AsyncMock(return_value="x"))
    url = asyncio.run(
        run_reuse_webapp_payment(
            desc, _webapp_ctx(_FakeService(configured=False)), SimpleNamespace()
        )
    )
    assert url is None
    desc.reuse.assert_not_awaited()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
