from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from bot.handlers.user.promo_user import process_promo_code_input
from bot.services.promo_code_service import PromoCheckoutRequired


class PromoUserHandlerTests(IsolatedAsyncioTestCase):
    async def test_checkout_required_code_opens_mini_app_from_bot_menu(self):
        user = SimpleNamespace(id=42, username="u", first_name="User")
        message = SimpleNamespace(
            text="save20",
            from_user=user,
            answer=AsyncMock(),
        )
        state = SimpleNamespace(
            get_state=AsyncMock(return_value="UserPromoStates:waiting_for_promo_code"),
            clear=AsyncMock(),
        )
        settings = SimpleNamespace(
            DEFAULT_LANGUAGE="en",
            LOG_SUSPICIOUS_ACTIVITY=False,
            SUBSCRIPTION_MINI_APP_URL="https://app.example.com/webapp?lang=en",
        )
        i18n = SimpleNamespace(
            gettext=lambda _lang, key, **kw: (
                f"checkout:{kw.get('effect')}" if key == "promo_code_requires_checkout" else key
            )
        )
        service = SimpleNamespace(
            apply_promo_code=AsyncMock(
                return_value=(
                    True,
                    PromoCheckoutRequired(
                        code="SAVE20",
                        effect_summary="-20%",
                        applies_to="subscription",
                    ),
                )
            )
        )
        session = SimpleNamespace(commit=AsyncMock())

        await process_promo_code_input(
            message=message,
            state=state,
            settings=settings,
            i18n_data={"current_language": "en", "i18n_instance": i18n},
            promo_code_service=service,
            subscription_service=SimpleNamespace(),
            bot=SimpleNamespace(),
            session=session,
        )

        session.commit.assert_awaited_once()
        state.clear.assert_awaited_once()
        service.apply_promo_code.assert_awaited_once_with(session, 42, "save20", "en")
        message.answer.assert_awaited_once()
        _, kwargs = message.answer.await_args
        assert kwargs["parse_mode"] == "HTML"
        assert kwargs["reply_markup"].inline_keyboard[0][0].web_app.url == (
            "https://app.example.com/webapp?lang=en&startapp=promo_SAVE20"
        )
