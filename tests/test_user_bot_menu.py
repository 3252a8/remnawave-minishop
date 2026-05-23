import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from bot.app.web import subscription_webapp
from bot.handlers.user import referral
from bot.handlers.user.subscription.core import _with_subscription_purchase_description
from bot.keyboards.inline.user_keyboards import (
    get_bot_interface_inline_keyboard,
    get_connect_and_main_keyboard,
    get_information_links_keyboard,
    get_language_selection_keyboard,
    get_main_menu_inline_keyboard,
    get_payment_method_keyboard,
    get_referral_link_keyboard,
    get_subscription_options_keyboard,
    get_tariff_catalog_keyboard,
    get_tariff_periods_keyboard,
    payment_methods_back_callback,
    payment_options_back_callback,
)


class JsonI18nStub:
    def __init__(self):
        self.translations = json.loads(Path("locales/en.json").read_text(encoding="utf-8"))

    def gettext(self, lang, key, **kwargs):
        text = self.translations[key]
        return text.format(**kwargs) if kwargs else text


class UserBotMenuTests(unittest.TestCase):
    def setUp(self):
        self.i18n = JsonI18nStub()
        self.settings = SimpleNamespace(
            SUBSCRIPTION_MINI_APP_URL="https://app.example.com/",
            SUPPORT_LINK="https://t.me/support",
            PRIVACY_POLICY_URL="https://example.com/privacy",
            USER_AGREEMENT_URL="https://example.com/agreement",
            TERMS_OF_SERVICE_URL="",
            TRIAL_ENABLED=True,
            SERVER_STATUS_URL="",
            SUBSCRIPTION_GUIDES_ENABLED=True,
            SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED=False,
            SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED=True,
            SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED=False,
            SUBSCRIPTION_PAGE_CONFIG_JSON="",
            PANEL_API_URL="https://panel.example.com",
            PANEL_API_KEY="token",
        )

    def _callback_data(self, markup):
        return [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        ]

    def test_main_menu_exposes_bot_menu_and_information(self):
        markup = get_main_menu_inline_keyboard("en", self.i18n, self.settings)

        callbacks = self._callback_data(markup)

        self.assertIn("main_action:bot_interface", callbacks)
        self.assertIn("main_action:info", callbacks)

    def test_bot_interface_buttons_return_to_bot_interface(self):
        markup = get_bot_interface_inline_keyboard("en", self.i18n, self.settings)

        callbacks = self._callback_data(markup)

        self.assertIn("main_action:bot_subscribe", callbacks)
        self.assertIn("main_action:bot_my_subscription", callbacks)
        self.assertIn("main_action:bot_referral", callbacks)
        self.assertIn("main_action:bot_info", callbacks)
        self.assertIn("main_action:back_to_main", callbacks)

    def test_connect_keyboard_uses_subscription_url_when_bot_guides_disabled(self):
        markup = get_connect_and_main_keyboard(
            "en",
            self.i18n,
            self.settings,
            "https://sb.example.com/user",
            connect_button_url=None,
        )

        self.assertEqual(markup.inline_keyboard[0][0].url, "https://sb.example.com/user")
        self.assertIsNone(markup.inline_keyboard[0][0].web_app)

    def test_connect_keyboard_opens_install_guide_when_bot_guides_enabled(self):
        self.settings.SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED = True
        markup = get_connect_and_main_keyboard(
            "en",
            self.i18n,
            self.settings,
            "https://sb.example.com/user",
            install_share_url="https://app.example.com/s/8f559061460e8fede78ef18dce887236",
        )

        self.assertIsNone(markup.inline_keyboard[0][0].url)
        self.assertEqual(
            markup.inline_keyboard[0][0].web_app.url,
            "https://app.example.com/install",
        )
        self.assertEqual(
            markup.inline_keyboard[1][0].url,
            "https://app.example.com/s/8f559061460e8fede78ef18dce887236",
        )

    def test_nested_bot_menu_keyboards_can_target_bot_interface_back(self):
        subscription_markup = get_subscription_options_keyboard(
            {1: 100},
            "RUB",
            "en",
            self.i18n,
            back_callback="main_action:bot_interface",
        )
        referral_markup = get_referral_link_keyboard(
            "en",
            self.i18n,
            back_callback="main_action:bot_interface",
        )
        info_markup = get_information_links_keyboard(
            "en",
            self.i18n,
            "https://example.com/privacy",
            "https://example.com/agreement",
            back_callback="main_action:bot_interface",
        )
        language_markup = get_language_selection_keyboard(
            self.i18n,
            "en",
            back_callback="main_action:bot_interface",
        )

        self.assertIn("main_action:bot_interface", self._callback_data(subscription_markup))
        self.assertIn("main_action:bot_interface", self._callback_data(referral_markup))
        self.assertIn("main_action:bot_interface", self._callback_data(info_markup))
        self.assertIn("set_lang_ru:bot", self._callback_data(language_markup))
        self.assertIn("subscribe_period:1:bot", self._callback_data(subscription_markup))

    def test_subscription_purchase_description_is_prepended_before_period_selection(self):
        settings = SimpleNamespace(
            subscription_purchase_description=lambda language: f"Description {language}"
        )

        self.assertEqual(
            _with_subscription_purchase_description(
                "Choose period",
                settings,
                "en",
                include=True,
            ),
            "Description en\n\nChoose period",
        )
        self.assertEqual(
            _with_subscription_purchase_description(
                "Choose traffic",
                settings,
                "en",
                include=False,
            ),
            "Choose traffic",
        )

    def test_payment_navigation_context_keeps_bot_menu_source(self):
        settings = SimpleNamespace(
            payment_methods_order=[],
            PLATEGA_ENABLED=False,
            PLATEGA_SBP_ENABLED=False,
            PLATEGA_CRYPTO_ENABLED=False,
        )
        markup = get_payment_method_keyboard(
            1,
            100,
            None,
            "RUB",
            "en",
            self.i18n,
            settings,
            sale_mode="subscription|bot",
        )

        self.assertIn("main_action:bot_subscribe", self._callback_data(markup))
        self.assertEqual(
            payment_methods_back_callback("1", "subscription|bot"),
            "subscribe_period:1:bot",
        )

    def test_tariff_back_buttons_return_to_previous_level(self):
        tariff = SimpleNamespace(
            key="basic",
            billing_model="period",
            enabled_periods=[1],
            name=lambda _lang: "Basic",
            description=lambda _lang: "Basic plan",
            min_period_price_rub=lambda: 100,
            period_price=lambda months, currency: (
                100 if months == 1 and currency == "rub" else None
            ),
        )
        settings = SimpleNamespace(DEFAULT_CURRENCY_SYMBOL="RUB")

        catalog = get_tariff_catalog_keyboard(
            [tariff],
            "en",
            self.i18n,
            back_callback="main_action:bot_interface",
        )
        periods = get_tariff_periods_keyboard(
            tariff,
            "en",
            self.i18n,
            settings,
            back_callback="main_action:bot_subscribe",
            callback_context="bot",
        )

        self.assertIn("tariff:select:basic:bot", self._callback_data(catalog))
        self.assertIn("main_action:bot_interface", self._callback_data(catalog))
        self.assertIn("tariff:period:basic:1:bot", self._callback_data(periods))
        self.assertIn("main_action:bot_subscribe", self._callback_data(periods))
        self.assertEqual(
            payment_options_back_callback("subscription@basic|bot"),
            "tariff:select:basic:bot",
        )
        self.assertEqual(
            payment_methods_back_callback("1", "subscription@basic|bot"),
            "tariff:period:basic:1:bot",
        )

    def test_webapp_referral_link_uses_ref_query_and_is_normalized(self):
        link = referral._build_webapp_referral_link(
            "https://app.example.com/invite?utm=channel",
            "AbC123xYz",
        )

        self.assertEqual(
            link,
            "https://app.example.com/invite?utm=channel&ref=uAbC123xYz",
        )
        self.assertEqual(subscription_webapp._normalize_referral_param("uAbC123xYz"), "ABC123XYZ")
        self.assertEqual(
            subscription_webapp._normalize_referral_param("ref_uAbC123xYz"), "ABC123XYZ"
        )

    def test_referral_text_places_web_link_after_telegram_link(self):
        text = self.i18n.gettext(
            "en",
            "referral_program_info_new",
            referral_link="https://t.me/bot?start=ref_uABC123XYZ",
            webapp_link_section=self.i18n.gettext(
                "en",
                "referral_webapp_link_line",
                webapp_referral_link="https://app.example.com/?ref=uABC123XYZ",
            ),
            bonus_details="bonus",
            invited_count=1,
            purchased_count=0,
        )

        self.assertLess(text.index("Telegram link:"), text.index("Web link:"))
        self.assertLess(text.index("Web link:"), text.index("Invitation bonuses:"))
