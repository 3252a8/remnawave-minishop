import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot.middlewares.ban_check_middleware import BanCheckMiddleware


class SubscriptionSuspensionBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_menu_and_support_reach_handlers_and_old_personal_checkouts_do_not(self):
        middleware = BanCheckMiddleware(Mock(), Mock())
        account = SimpleNamespace(is_banned=False, language_code="ru", suspended_subscription_id=82)
        data = {"session": Mock(), "event_from_user": SimpleNamespace(id=42), "bot": Mock()}
        with patch("db.dal.user_dal.get_user_by_telegram_id", AsyncMock(return_value=account)):
            for button, invoice, allowed in (
                (None, None, True),
                ("support", None, True),
                ("pay_stars:1:10:subscription", None, False),
                (None, "1:1:subscription", False),
                (None, "1:1:subscription|gift", True),
            ):
                callback = SimpleNamespace(data=button, answer=AsyncMock()) if button else None
                checkout = (
                    SimpleNamespace(invoice_payload=invoice, answer=AsyncMock())
                    if invoice
                    else None
                )
                event = SimpleNamespace(callback_query=callback, pre_checkout_query=checkout)
                handler = AsyncMock()
                with self.subTest(button=button, invoice=invoice):
                    await middleware(handler, event, data)
                    self.assertEqual(handler.await_count, int(allowed))
                    if not allowed:
                        (callback or checkout).answer.assert_awaited_once()
