"""Regression test for the YooKassa webhook 500 caused by a missing class attr.

A real production crash looked like::

    YooKassa Webhook Parsed: Event='payment.succeeded'
    AttributeError: 'SubscriptionService' object has no attribute '_PROVIDER_LABELS'

The fix wires ``_PROVIDER_LABELS`` onto ``PaymentContextMixin`` so the
payment-success email lookup can never blow up the webhook handler again.
These tests pin the contract end-to-end.
"""

import unittest
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import patch

from bot.services.subscription_service_impl import payments as payments_module
from bot.services.subscription_service_impl.payments import PaymentContextMixin

# Provider strings that flow into ``Subscription.provider`` — every value
# present at a real call site must be representable here.
_PROVIDERS_FROM_CALLERS = {
    "yookassa",
    "freekassa",
    "platega",
    "severpay",
    "wata",
    "lava",
    "cryptopay",
    "paykilla",
    "cloudpayments",
    "pally",
    "telegram_stars",
}


class ProviderLabelsTests(unittest.TestCase):
    def test_attribute_is_defined_on_mixin(self):
        # The crash was specifically ``AttributeError`` — guard against that.
        self.assertTrue(hasattr(PaymentContextMixin, "_PROVIDER_LABELS"))
        self.assertIsInstance(PaymentContextMixin._PROVIDER_LABELS, dict)

    def test_every_runtime_provider_has_a_label(self):
        labels = PaymentContextMixin._PROVIDER_LABELS
        for provider in _PROVIDERS_FROM_CALLERS:
            with self.subTest(provider=provider):
                self.assertIn(provider, labels)
                self.assertTrue(labels[provider])  # non-empty display text

    def test_labels_are_keyed_by_lowercase_string(self):
        # Lookup site does ``self._PROVIDER_LABELS.get((provider or '').lower())``
        # so keys must already be lowercase to ever resolve.
        for key in PaymentContextMixin._PROVIDER_LABELS:
            self.assertEqual(key, key.lower())


class _FakeUser(SimpleNamespace):
    pass


class _FakeEmailService:
    instances: ClassVar[list["_FakeEmailService"]] = []

    def __init__(self, settings, i18n=None):
        self.settings = settings
        self.i18n = i18n
        self.sent: list[dict] = []
        _FakeEmailService.instances.append(self)

    async def send_rendered_email(self, *, email, content):
        self.sent.append({"email": email, "content": content})


class SendPaymentSuccessEmailTests(unittest.IsolatedAsyncioTestCase):
    """Exercise the exact code path that hit the AttributeError in prod."""

    def setUp(self) -> None:
        _FakeEmailService.instances = []

    async def _invoke(self, provider: str) -> dict:
        captured: dict = {}

        def fake_render(settings, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(subject="s", text="t", html="<p>h</p>")

        mixin = PaymentContextMixin()
        mixin.settings = SimpleNamespace(
            email_auth_configured=True,
            DEFAULT_LANGUAGE="ru",
            DEFAULT_CURRENCY_SYMBOL="RUB",
            SUBSCRIPTION_MINI_APP_URL="https://app.example.com/",
        )
        user = _FakeUser(user_id=42, email="buyer@example.com", language_code="en")

        with (
            patch.object(payments_module, "render_payment_success", fake_render),
            patch.object(payments_module, "EmailAuthService", _FakeEmailService),
        ):
            await mixin._send_payment_success_email(
                db_user=user,
                sale_mode="subscription",
                months=3,
                traffic_gb=None,
                payment_amount=450.0,
                end_date=None,
                provider=provider,
            )
        return captured

    async def test_yookassa_resolves_to_human_label(self):
        kwargs = await self._invoke("yookassa")
        self.assertEqual(kwargs.get("provider_label"), "YooKassa")
        self.assertEqual(len(_FakeEmailService.instances), 1)
        self.assertEqual(len(_FakeEmailService.instances[0].sent), 1)

    async def test_unknown_provider_renders_as_none_without_raising(self):
        # The email template treats ``None`` as "skip the provider row" — we
        # need that fallback because new providers may ship before labels do.
        kwargs = await self._invoke("paypal_someday")
        self.assertIsNone(kwargs.get("provider_label"))

    async def test_provider_lookup_is_case_insensitive(self):
        kwargs = await self._invoke("YooKassa")
        self.assertEqual(kwargs.get("provider_label"), "YooKassa")

    async def test_skips_email_when_smtp_unconfigured(self):
        mixin = PaymentContextMixin()
        mixin.settings = SimpleNamespace(email_auth_configured=False)
        user = _FakeUser(user_id=1, email="x@y.z", language_code="en")

        with patch.object(payments_module, "EmailAuthService", _FakeEmailService):
            await mixin._send_payment_success_email(
                db_user=user,
                sale_mode="subscription",
                months=1,
                traffic_gb=None,
                payment_amount=10.0,
                end_date=None,
                provider="yookassa",
            )

        self.assertEqual(_FakeEmailService.instances, [])

    async def test_skips_email_when_user_has_no_email(self):
        mixin = PaymentContextMixin()
        mixin.settings = SimpleNamespace(
            email_auth_configured=True,
            DEFAULT_LANGUAGE="ru",
            DEFAULT_CURRENCY_SYMBOL="RUB",
            SUBSCRIPTION_MINI_APP_URL="",
        )
        user = _FakeUser(user_id=1, email="   ", language_code="en")

        with patch.object(payments_module, "EmailAuthService", _FakeEmailService):
            await mixin._send_payment_success_email(
                db_user=user,
                sale_mode="subscription",
                months=1,
                traffic_gb=None,
                payment_amount=10.0,
                end_date=None,
                provider="yookassa",
            )

        self.assertEqual(_FakeEmailService.instances, [])

    async def test_render_exceptions_are_swallowed(self):
        # The mail path must never block payment processing — this is exactly
        # the contract that the original crash violated for a different reason.
        def boom(*args, **kwargs):
            raise RuntimeError("smtp on fire")

        mixin = PaymentContextMixin()
        mixin.settings = SimpleNamespace(
            email_auth_configured=True,
            DEFAULT_LANGUAGE="ru",
            DEFAULT_CURRENCY_SYMBOL="RUB",
            SUBSCRIPTION_MINI_APP_URL="",
        )
        user = _FakeUser(user_id=1, email="x@y.z", language_code="en")

        with patch.object(payments_module, "render_payment_success", boom):
            # No assertion needed — completion without raising IS the assertion.
            await mixin._send_payment_success_email(
                db_user=user,
                sale_mode="subscription",
                months=1,
                traffic_gb=None,
                payment_amount=10.0,
                end_date=None,
                provider="yookassa",
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
