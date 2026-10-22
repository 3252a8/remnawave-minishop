"""Gateway outages offer only the remaining, previously visible payment actions."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from aiogram import types

from bot.payment_providers import registry
from bot.payment_providers.base import PaymentMethodGroup, PaymentProviderSpec
from bot.payment_providers.shared.callbacks import PaymentCallbackParts
from bot.payment_providers.shared.common import payment_provider_unavailable
from bot.payment_providers.shared.payment_fallback import payment_fallback_keyboard
from config.settings import Settings


@pytest.mark.parametrize("status", [401, 403, 429, 500, 502, 503, 504, 599])
def test_gateway_rejection_without_checkout_allows_an_alternative(status: int) -> None:
    assert payment_provider_unavailable(
        {"status": status, "message": "invalid_json", "raw": "no healthy upstream"},
        api_success=False,
        payment_url=None,
        provider_payment_id=None,
    )


@pytest.mark.parametrize("response", [None, {}, {"message": "timeout"}, {"status": 400}])
def test_ambiguous_or_invalid_order_failure_does_not_offer_an_alternative(
    response: object,
) -> None:
    assert not payment_provider_unavailable(
        response, api_success=False, payment_url=None, provider_payment_id=None
    )


@pytest.mark.parametrize(
    ("api_success", "url", "provider_id"),
    [(True, None, None), (False, "https://pay.example/link", None), (False, None, "id")],
)
def test_evidence_of_an_existing_checkout_prevents_alternative(
    api_success: bool, url: str | None, provider_id: str | None
) -> None:
    assert not payment_provider_unavailable(
        {"status": 503},
        api_success=api_success,
        payment_url=url,
        provider_payment_id=provider_id,
    )


def _spec(method: str) -> PaymentProviderSpec:
    return PaymentProviderSpec(
        id=method,
        provider_key=method,
        label=method,
        pending_status=f"pending_{method}",
        enabled=lambda _settings: True,
        callback_prefix=f"pay_{method}",
        payment_group="fiat",
    )


def _callback(selected: str, buttons: list[tuple[str, str]]) -> types.CallbackQuery:
    return types.CallbackQuery(
        id="test-callback",
        from_user=types.User(id=123, is_bot=False, first_name="Test"),
        chat_instance="test-chat",
        data=selected,
        message=types.Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=types.Chat(id=123, type="private"),
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text=label, callback_data=data)]
                    for label, data in buttons
                ]
            ),
        ),
    )


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="test",
        POSTGRES_PASSWORD="test",
        TARIFFS_CONFIG_PATH="missing-tariffs.json",
        DEFAULT_CURRENCY_SYMBOL="RUB",
        PAYMENT_METHODS_ORDER="alpha,bravo,charlie,stars",
    )


def _translate(key: str, **params: object) -> str:
    return f"{key}:{params.get('method', '')}"


def test_next_method_wraps_within_the_same_group_and_preserves_exact_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs = (
        _spec("alpha"),
        _spec("bravo"),
        _spec("charlie"),
        replace(_spec("stars"), price_source="stars", payment_group="stars"),
    )
    monkeypatch.setattr(registry, "PAYMENT_PROVIDER_SPECS", specs)
    mode = "subscription@basic|d30|p7"
    callback = _callback(
        f"pay_charlie:1:200:{mode}",
        [
            (spec.id, f"pay_{spec.id}:1:{99 if spec.id == 'stars' else 200}:{mode}")
            for spec in specs
        ],
    )
    markup, has_alternative = payment_fallback_keyboard(
        callback,
        settings=_settings(),
        parts=PaymentCallbackParts(months=1, price=200, sale_mode=mode),
        translator=_translate,
        language="en",
    )
    assert has_alternative
    actions = [row[0].callback_data for row in markup.inline_keyboard]
    assert actions[:-1] == [
        f"pay_alpha:1:200:{mode}",
        f"pay_bravo:1:200:{mode}",
    ]
    assert markup.inline_keyboard[0][0].text.startswith("payment_try_alternative:")
    assert not any(action and action.startswith("pay_charlie:") for action in actions)


@pytest.mark.parametrize("group", ["fiat", "crypto", "stars", "mixed", None])
def test_alternatives_keep_the_funding_group_and_skip_the_failed_provider(
    monkeypatch: pytest.MonkeyPatch, group: PaymentMethodGroup | None
) -> None:
    specs = (
        replace(_spec("alpha"), payment_group=group, service_key="first"),
        replace(_spec("bravo"), payment_group=group, service_key="first"),
        replace(_spec("charlie"), payment_group=group, service_key="second"),
        replace(_spec("stars"), payment_group="crypto" if group != "crypto" else "fiat"),
    )
    monkeypatch.setattr(registry, "PAYMENT_PROVIDER_SPECS", specs)
    callback = _callback(
        "pay_alpha:1:200:subscription",
        [(spec.id, f"pay_{spec.id}:1:200:subscription") for spec in specs],
    )
    markup, has_alternative = payment_fallback_keyboard(
        callback,
        settings=_settings(),
        parts=PaymentCallbackParts(months=1, price=200, sale_mode="subscription"),
        translator=_translate,
        language="en",
    )
    assert has_alternative is (group is not None)
    expected = "pay_charlie:1:200:subscription" if group is not None else callback.data
    assert [row[0].callback_data for row in markup.inline_keyboard][:-1] == [expected]


def test_hidden_disabled_wrong_order_currency_and_context_methods_are_excluded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs = (
        _spec("alpha"),
        _spec("hidden"),
        _spec("disabled"),
        replace(_spec("currency"), supported_currencies=("USD",)),
        replace(_spec("context"), payment_context_resolver=lambda *_args: False),
        replace(_spec("promo"), checkout_promo_resolver=lambda *_args: False),
        _spec("bravo"),
    )
    # A currently disabled method must not survive an old Telegram keyboard.
    specs = tuple(
        PaymentProviderSpec(
            id="disabled",
            provider_key="disabled",
            label="disabled",
            pending_status="pending",
            callback_prefix="pay_disabled",
            enabled=lambda _settings: False,
            admin_only_enabled=lambda _settings: True,
        )
        if spec.id == "disabled"
        else spec
        for spec in specs
    )
    monkeypatch.setattr(registry, "PAYMENT_PROVIDER_SPECS", specs)
    mode = "subscription@basic"
    callback = _callback(
        f"pay_alpha:1:200:{mode}",
        [
            (spec.id, f"pay_{spec.id}:{2 if spec.id == 'bravo' else 1}:200:{mode}")
            for spec in specs
            if spec.id != "hidden"
        ],
    )
    parts = PaymentCallbackParts(months=1, price=200, sale_mode=mode)
    # Test the same promo guard used by the regular method list without creating an order.
    monkeypatch.setattr(
        PaymentProviderSpec, "is_checkout_promo_supported", lambda spec, *_args: spec.id != "promo"
    )
    markup, has_alternative = payment_fallback_keyboard(
        callback, settings=_settings(), parts=parts, translator=_translate, language="en"
    )
    assert not has_alternative
    assert markup.inline_keyboard[0][0].callback_data == callback.data
    assert markup.inline_keyboard[0][0].text.startswith("payment_retry:")
    assert len(markup.inline_keyboard) == 2


def test_chained_failures_do_not_restore_failed_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    specs = (_spec("alpha"), _spec("bravo"), _spec("charlie"))
    monkeypatch.setattr(registry, "PAYMENT_PROVIDER_SPECS", specs)
    parts = PaymentCallbackParts(months=1, price=200, sale_mode="subscription")
    callback = _callback(
        "pay_alpha:1:200:subscription", [(s.id, f"pay_{s.id}:1:200:subscription") for s in specs]
    )
    markup, _ = payment_fallback_keyboard(
        callback, settings=_settings(), parts=parts, translator=_translate, language="en"
    )
    assert isinstance(callback.message, types.Message)
    callback = callback.model_copy(
        update={
            "message": callback.message.model_copy(update={"reply_markup": markup}),
            "data": "pay_bravo:1:200:subscription",
        }
    )
    markup, has_alternative = payment_fallback_keyboard(
        callback, settings=_settings(), parts=parts, translator=_translate, language="en"
    )
    assert has_alternative
    assert [row[0].callback_data for row in markup.inline_keyboard][:-1] == [
        "pay_charlie:1:200:subscription"
    ]
