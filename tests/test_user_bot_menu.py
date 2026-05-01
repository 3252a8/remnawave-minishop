import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from bot.app.web import subscription_webapp
from bot.handlers.user import referral
from bot.keyboards.inline.user_keyboards import (
    get_bot_interface_inline_keyboard,
    get_information_links_keyboard,
    get_language_selection_keyboard,
    get_main_menu_inline_keyboard,
    get_referral_link_keyboard,
    get_subscription_options_keyboard,
)


class JsonI18nStub:
    def __init__(self):
        self.translations = json.loads(
            Path("locales/en.json").read_text(encoding="utf-8")
        )

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
        self.assertEqual(subscription_webapp._normalize_referral_param("ref_uAbC123xYz"), "ABC123XYZ")

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
