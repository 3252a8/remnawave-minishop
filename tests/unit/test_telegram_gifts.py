from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.app.web.webapp.gifts import GiftView
from bot.handlers.user import gifts
from bot.handlers.user.start_callbacks import verify_channel_subscription_callback
from bot.services.gift_links import gift_telegram_url, redact_gift_tokens
from bot.services.subscription_gifts import GiftError
from bot.services.subscription_order_terms import freeze_subscription_terms
from config.tariffs_config import TariffsConfig
from db.gift_models import SubscriptionGift
from db.models import Payment, Subscription, User


class TelegramGiftTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.token = "R" * 43
        self.settings = SimpleNamespace(
            DEFAULT_LANGUAGE="en",
            GIFTS_ENABLED=False,
            DISABLE_WELCOME_MESSAGE=False,
            USER_HWID_DEVICE_LIMIT=3,
            USER_TRAFFIC_STRATEGY="NO_RESET",
            tariffs_config=TariffsConfig.model_validate(
                {
                    "schema_version": 2,
                    "period_unit": "day",
                    "default_tariff": "base",
                    "tariffs": [
                        {
                            "key": "base",
                            "billing_model": "period",
                            "period_unit": "day",
                            "monthly_gb": 100,
                            "enabled_periods": [7],
                            "prices_rub": {"7": 100},
                        }
                    ],
                }
            ),
        )
        self.user = User(user_id=20, telegram_id=999, minishop_id="ms_recipient", is_banned=False)
        self.gift = SubscriptionGift(
            gift_id=8, payment_id=77, purchaser_id=10, token=self.token, status="ready"
        )
        self.payment = Payment(
            payment_id=77,
            user_id=10,
            status="succeeded",
            sale_mode="subscription@base|d7|gift",
            tariff_key="base",
            amount=100,
            subscription_duration_days=7,
            subscription_terms_snapshot=freeze_subscription_terms(
                self.settings, "subscription@base|d7|gift"
            ),
        )
        self.message = SimpleNamespace(
            chat=SimpleNamespace(type="private", id=999),
            answer=AsyncMock(),
            edit_text=AsyncMock(),
        )
        self.callback = SimpleNamespace(
            data=f"gift:claim:{self.token}",
            message=self.message,
            answer=AsyncMock(),
            from_user=SimpleNamespace(id=999, full_name="Recipient"),
        )
        self.state = AsyncMock()
        self.state.get_data.return_value = {"pending_gift_token": self.token}
        self.session = AsyncMock()
        self.i18n_data = {
            "current_language": "en",
            "i18n_instance": SimpleNamespace(
                gettext=lambda lang, key, **kw: key + (" " + str(kw) if kw else "")
            ),
        }
        self.claim = AsyncMock(return_value=self.gift)
        self.channel = AsyncMock(return_value=True)
        self.active = AsyncMock(return_value=None)
        self.invalidate = AsyncMock()
        self.menu = AsyncMock()
        for name, value in (
            (
                "bot.handlers.user.gifts.user_dal.get_user_by_telegram_id",
                AsyncMock(return_value=self.user),
            ),
            ("bot.handlers.user.gifts.gift_dal.by_token", AsyncMock(return_value=self.gift)),
            (
                "bot.handlers.user.gifts.payment_dal.get_payment_by_db_id",
                AsyncMock(return_value=self.payment),
            ),
            (
                "bot.handlers.user.gifts.subscription_dal.get_active_subscription_by_user_id",
                self.active,
            ),
            ("bot.handlers.user.gifts.claim_gift", self.claim),
            ("bot.handlers.user.gifts.ensure_required_channel_subscription", self.channel),
            ("bot.handlers.user.gifts.invalidate_webapp_user_caches", self.invalidate),
            ("bot.handlers.user.start_menus.send_main_menu", self.menu),
        ):
            guard = patch(name, value)
            guard.start()
            self.addCleanup(guard.stop)

    async def preview(self):
        await gifts.show_gift_preview(
            self.message,
            token=self.token,
            user=self.user,
            settings=self.settings,
            i18n_data=self.i18n_data,
            session=self.session,
        )

    async def confirm(self):
        await gifts.claim_gift_callback(
            self.callback, self.state, self.settings, self.i18n_data, AsyncMock(), self.session
        )

    async def test_preview_shows_frozen_terms_account_and_requires_confirmation(self):
        self.settings.tariffs_config = None
        await self.preview()
        self.claim.assert_not_awaited()
        text = self.message.answer.await_args.args[0]
        self.assertIn("ms_recipient", text)
        self.assertIn("100.0", text)
        self.assertIn("'count': 3", text)
        keyboard = self.message.answer.await_args.kwargs["reply_markup"]
        data = keyboard.inline_keyboard[0][0].callback_data
        self.assertEqual(data, f"gift:claim:{self.token}")
        self.assertLessEqual(len(data.encode()), 64)

    async def test_confirmation_uses_internal_account_even_when_purchase_disabled(self):
        await self.confirm()
        self.assertEqual(self.claim.await_args.kwargs["user_id"], 20)
        self.assertEqual(self.claim.await_args.kwargs["token"], self.token)
        self.invalidate.assert_awaited_once_with(self.settings, 20, include_devices=True)
        self.state.update_data.assert_any_await(pending_gift_token=None)
        self.menu.assert_awaited_once()

    async def test_channel_gate_preserves_pending_gift_without_claim(self):
        self.channel.return_value = False
        await self.confirm()
        self.state.update_data.assert_awaited_once_with(pending_gift_token=self.token)
        self.claim.assert_not_awaited()

    async def test_channel_verification_resumes_preview_instead_of_claim(self):
        with patch(
            "bot.handlers.user.start_callbacks.ensure_required_channel_subscription", self.channel
        ):
            await verify_channel_subscription_callback(
                self.callback, self.settings, self.i18n_data, AsyncMock(), self.session, self.state
            )
        self.assertIn("reply_markup", self.message.answer.await_args.kwargs)
        self.claim.assert_not_awaited()
        self.menu.assert_not_awaited()

    async def test_invalid_banned_and_nonprivate_callbacks_cannot_claim(self):
        for mutation in ("token", "banned", "group"):
            with self.subTest(mutation=mutation):
                self.callback.data = (
                    "gift:claim:bad" if mutation == "token" else f"gift:claim:{self.token}"
                )
                self.user.is_banned = mutation == "banned"
                self.message.chat.type = "group" if mutation == "group" else "private"
                await self.confirm()
        self.claim.assert_not_awaited()

    async def test_claim_errors_keep_retry_available_and_do_not_report_success(self):
        for code in (
            "gift_used",
            "gift_own",
            "gift_unavailable",
            "gift_tariff_conflict",
            "gift_recurring_conflict",
            "gift_other_activation_pending",
            "gift_activation_retry",
        ):
            with self.subTest(code=code):
                self.claim.side_effect = GiftError(code)
                await self.confirm()
                self.message.answer.assert_awaited_with(f"wa_{code}")
        self.invalidate.assert_not_awaited()
        self.menu.assert_not_awaited()
        self.assertNotIn(
            None,
            [c.kwargs.get("pending_gift_token") for c in self.state.update_data.await_args_list],
        )

    async def test_preview_rejects_own_used_and_revoked_gifts(self):
        for status, recipient, purchaser, payment_status, key in (
            ("ready", None, 20, "succeeded", "own"),
            ("activating", 30, 10, "succeeded", "used"),
            ("activated", 30, 10, "succeeded", "used"),
            ("revoked", None, 10, "succeeded", "unavailable"),
            ("ready", None, 10, "refunded", "unavailable"),
        ):
            with self.subTest(key=key):
                self.gift.status, self.gift.recipient_id, self.gift.purchaser_id = (
                    status,
                    recipient,
                    purchaser,
                )
                self.payment.status = payment_status
                await self.preview()
                self.message.answer.assert_awaited_with(f"wa_gift_{key}")

    async def test_conflict_hides_confirmation_but_reserved_gift_can_retry(self):
        self.active.return_value = Subscription(
            tariff_key="other", provider="manual", auto_renew_enabled=False
        )
        await self.preview()
        keyboard = self.message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(len(keyboard.inline_keyboard), 1)
        self.gift.status, self.gift.recipient_id = "activating", 20
        await self.preview()
        keyboard = self.message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(keyboard.inline_keyboard[0][0].text, "wa_gift_retry")

    def test_link_contract_preserves_web_link_and_owner_visibility(self):
        self.gift.created_at = datetime.now(UTC)
        for viewer, status, expected in (
            (10, "ready", True),
            (20, "ready", False),
            (10, "activated", False),
        ):
            self.gift.status = status
            view = GiftView.from_orm_gift(
                self.gift,
                self.payment,
                viewer_id=viewer,
                base_url="https://example.test/app",
                bot_username="example_bot",
            )
            self.assertEqual(bool(view.telegram_link), expected)
            if expected:
                self.assertEqual(view.link, f"https://example.test/?gift={self.token}")
                self.assertEqual(
                    view.telegram_link, f"https://t.me/example_bot?start=gift_{self.token}"
                )
        self.assertIsNone(gift_telegram_url("", self.token))
        self.assertIsNone(gift_telegram_url("example_bot", "bad"))

    def test_secret_redaction_covers_start_callback_and_raw_update(self):
        for text in (
            f"/start@ExampleBot gift_{self.token}",
            f"gift:claim:{self.token}",
            '{"text":"/start gift_' + self.token + '"}',
        ):
            self.assertNotIn(self.token, redact_gift_tokens(text))
            self.assertIn("[redacted]", redact_gift_tokens(text))
