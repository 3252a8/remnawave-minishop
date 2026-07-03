"""Direct unit tests for the shared link-payment engine.

These pin the orchestration independently of any concrete provider: a synthetic
descriptor + fakes drive the three engine flows, and the heavy shared
collaborators are patched on the engine module namespace.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.payment_providers.shared import link_flow
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
    parts = SimpleNamespace(price=100.0, months=1, sale_mode="subscription")
    monkeypatch.setattr(link_flow, "parse_payment_callback", lambda data: parts)

    async def _quote(**kwargs):
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


def test_webapp_payment_unconfigured_returns_unavailable(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(link_flow, "payment_unavailable", lambda: sentinel)
    desc = _descriptor()
    result = asyncio.run(run_webapp_payment(desc, _webapp_ctx(_FakeService(configured=False))))
    assert result is sentinel


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
