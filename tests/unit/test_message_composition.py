"""The shared message composition contract used by broadcasts, single-user
messages, and plugin-owned sequences."""

from __future__ import annotations

import unittest
from typing import Any, ClassVar, cast
from unittest.mock import patch

from aiogram.types import InlineKeyboardMarkup

from bot.services import outbound_messaging
from bot.services.message_composition import (
    MESSAGE_BUTTON_LABEL_KEYS,
    MessageButton,
    MessageButtonInput,
    MessageValidationError,
    email_links_for_buttons,
    message_promo_codes,
    normalize_message_channels,
    resolve_localized_text,
    resolve_message_buttons,
    telegram_markup_for_buttons,
)

MINI_APP_HTTPS = "https://shop.example/app"
MINI_APP_HTTP = "http://shop.example/app"


def _resolve(
    *buttons: MessageButtonInput,
    mini_app_url: str = MINI_APP_HTTPS,
) -> list[MessageButton]:
    return list(
        resolve_message_buttons(
            list(buttons),
            mini_app_url=mini_app_url,
            bot_username="shop_bot",
        )
    )


class MiniAppSectionButtonTests(unittest.TestCase):
    def test_section_button_opens_the_screen_inside_telegram(self) -> None:
        [button] = _resolve(
            MessageButtonInput(kind="webapp_section", label="Invite", section="invite")
        )

        # An https Mini App target becomes a web_app button, so the screen
        # opens authorized inside Telegram instead of an external browser.
        self.assertEqual(button.url, f"{MINI_APP_HTTPS}?startapp=invite")
        self.assertEqual(button.telegram_web_app_url, button.url)
        self.assertEqual(button.section, "invite")

    def test_plain_http_mini_app_falls_back_to_a_startapp_deep_link(self) -> None:
        [button] = _resolve(
            MessageButtonInput(kind="webapp_section", label="Support", section="support"),
            mini_app_url=MINI_APP_HTTP,
        )

        # Telegram refuses http web_app targets, so the t.me deep link keeps
        # the screen opening inside the Mini App rather than a browser tab.
        self.assertEqual(button.url, "https://t.me/shop_bot?startapp=support")
        self.assertIsNone(button.telegram_web_app_url)

    def test_plans_section_opens_checkout(self) -> None:
        [button] = _resolve(
            MessageButtonInput(kind="webapp_section", label="Plans", section="plans")
        )

        self.assertEqual(button.url, f"{MINI_APP_HTTPS}?startapp=plans")
        self.assertEqual(button.telegram_web_app_url, button.url)

    def test_partner_section_opens_the_partner_program(self) -> None:
        [button] = _resolve(
            MessageButtonInput(kind="webapp_section", label="Partner", section="partner")
        )

        self.assertEqual(button.url, f"{MINI_APP_HTTPS}?startapp=partner")
        self.assertEqual(button.telegram_web_app_url, button.url)
        self.assertEqual(button.section, "partner")

    def test_notifications_section_opens_notification_settings(self) -> None:
        [button] = _resolve(
            MessageButtonInput(
                kind="webapp_section", label="Notifications", section="notifications"
            )
        )

        self.assertEqual(button.url, f"{MINI_APP_HTTPS}?startapp=notifications")
        self.assertEqual(button.telegram_web_app_url, button.url)
        self.assertEqual(button.section, "notifications")

    def test_unknown_and_admin_sections_are_rejected(self) -> None:
        for section in ("", "tariffs", "admin", "Admin"):
            with self.subTest(section=section), self.assertRaises(MessageValidationError):
                _resolve(MessageButtonInput(kind="webapp_section", label="Go", section=section))


class MessageCompositionTests(unittest.TestCase):
    def test_plain_dataclass_inputs_need_no_http_schema(self) -> None:
        """A plugin composes buttons without importing the admin HTTP models."""

        resolved = _resolve(
            MessageButtonInput(kind="url", label="Plans", url="https://shop.example")
        )

        self.assertEqual(
            resolved,
            [MessageButton(label="Plans", url="https://shop.example", kind="url")],
        )

    def test_promo_webapp_button_opens_inside_the_mini_app(self) -> None:
        resolved = _resolve(
            MessageButtonInput(kind="promo_webapp", label="Apply", promo_code="SAVE10")
        )

        self.assertEqual(
            resolved[0].telegram_web_app_url,
            "https://shop.example/app?startapp=promo_SAVE10",
        )
        markup = telegram_markup_for_buttons(resolved)
        self.assertIsInstance(markup, InlineKeyboardMarkup)
        assert markup is not None
        inline = markup.inline_keyboard[0][0]
        # A web_app button keeps the customer inside Telegram; a url button
        # would hand the promo link to an external browser without the Mini
        # App authorization.
        self.assertIsNotNone(inline.web_app)
        self.assertIsNone(inline.url)

    def test_webapp_kind_opens_an_arbitrary_target_inside_telegram(self) -> None:
        resolved = _resolve(
            MessageButtonInput(kind="webapp", label="Plans", url=f"{MINI_APP_HTTPS}?startapp=plans")
        )

        self.assertEqual(resolved[0].telegram_web_app_url, f"{MINI_APP_HTTPS}?startapp=plans")
        markup = telegram_markup_for_buttons(resolved)
        assert markup is not None
        self.assertIsNotNone(markup.inline_keyboard[0][0].web_app)

    def test_webapp_kind_degrades_to_a_link_without_https(self) -> None:
        resolved = _resolve(MessageButtonInput(kind="webapp", label="Plans", url=MINI_APP_HTTP))

        self.assertIsNone(resolved[0].telegram_web_app_url)
        markup = telegram_markup_for_buttons(resolved)
        assert markup is not None
        self.assertEqual(markup.inline_keyboard[0][0].url, MINI_APP_HTTP)

    def test_promo_webapp_falls_back_to_a_startapp_deeplink_without_https(self) -> None:
        resolved = _resolve(
            MessageButtonInput(kind="promo_webapp", label="Apply", promo_code="SAVE10"),
            mini_app_url=MINI_APP_HTTP,
        )

        # Telegram refuses a plain-http web_app target, so the code still has
        # to reach the Mini App through t.me rather than a browser tab.
        self.assertIsNone(resolved[0].telegram_web_app_url)
        self.assertEqual(resolved[0].url, "https://t.me/shop_bot?startapp=promo_SAVE10")

    def test_promo_bot_button_deep_links_into_the_bot(self) -> None:
        resolved = _resolve(
            MessageButtonInput(kind="promo_bot", label="Apply", promo_code="SAVE10")
        )

        self.assertEqual(resolved[0].url, "https://t.me/shop_bot?start=promo_SAVE10")
        self.assertEqual(message_promo_codes(resolved), ["SAVE10"])
        self.assertEqual(
            email_links_for_buttons(resolved),
            [("Apply", "https://t.me/shop_bot?start=promo_SAVE10")],
        )

    def test_authoring_mistakes_carry_a_stable_code(self) -> None:
        cases = [
            (MessageButtonInput(kind="url", label="Plans"), "button_url_required"),
            (MessageButtonInput(kind="url", label="Plans", url="ftp://x"), "button_url_invalid"),
            (MessageButtonInput(kind="promo_bot", label="Apply"), "button_promo_code_required"),
            (
                MessageButtonInput(kind="promo_bot", label="Apply", promo_code="not valid"),
                "button_promo_code_invalid",
            ),
            (MessageButtonInput(kind="nope", label="Apply"), "button_kind_invalid"),
            (MessageButtonInput(kind="url", label="", url="https://x"), "button_label_required"),
        ]
        for button, code in cases:
            with self.subTest(code=code), self.assertRaises(MessageValidationError) as error:
                _resolve(button)
            self.assertEqual(error.exception.code, code)

    def test_too_many_buttons_are_rejected(self) -> None:
        buttons = [
            MessageButtonInput(kind="url", label=f"Link {index}", url="https://x")
            for index in range(5)
        ]
        with self.assertRaises(MessageValidationError) as error:
            resolve_message_buttons(
                list(buttons),
                mini_app_url=MINI_APP_HTTPS,
                bot_username="shop_bot",
            )
        self.assertEqual(error.exception.code, "too_many_buttons")

    def test_channels_are_deduplicated_and_ordered(self) -> None:
        self.assertEqual(
            normalize_message_channels(["email", "telegram", "email"]),
            ["telegram", "email"],
        )
        with self.assertRaises(MessageValidationError) as empty:
            normalize_message_channels([])
        self.assertEqual(empty.exception.code, "no_channels")
        with self.assertRaises(MessageValidationError) as unknown:
            normalize_message_channels(["sms"])
        self.assertEqual(unknown.exception.code, "invalid_channel")


class _FakeQueue:
    def __init__(self, captured: dict[str, Any]) -> None:
        self._captured = captured

    async def send_message(self, **kwargs: Any) -> None:
        self._captured.update(kwargs)


async def _no_audit(*_args: Any, **_kwargs: Any) -> None:
    return None


class OutboundButtonSeamTests(unittest.IsolatedAsyncioTestCase):
    async def _send(self, **kwargs: Any) -> dict[str, Any]:
        captured: dict[str, Any] = {}
        with (
            patch.object(outbound_messaging, "get_queue_manager", lambda: _FakeQueue(captured)),
            patch.object(outbound_messaging, "log_user_message_delivery", _no_audit),
        ):
            sent = await outbound_messaging.OutboundMessagingService(cast(Any, object())).send_text(
                None,
                user_id=42,
                text="hello",
                **kwargs,
            )
        captured["__sent__"] = sent
        return captured

    async def test_send_attaches_the_inline_keyboard(self) -> None:
        """The public send seam forwards buttons as a real inline keyboard."""

        buttons = _resolve(MessageButtonInput(kind="promo_bot", label="Apply", promo_code="SAVE10"))

        captured = await self._send(buttons=buttons)

        self.assertTrue(captured["__sent__"])
        markup = captured["reply_markup"]
        self.assertIsInstance(markup, InlineKeyboardMarkup)
        self.assertEqual(
            markup.inline_keyboard[0][0].url,
            "https://t.me/shop_bot?start=promo_SAVE10",
        )

    async def test_send_without_buttons_stays_keyboardless(self) -> None:
        captured = await self._send()

        self.assertIsNone(captured["reply_markup"])


if __name__ == "__main__":
    unittest.main()


class SingleUserAudienceTests(unittest.TestCase):
    def test_a_single_user_target_round_trips(self) -> None:
        from bot.services.audience_segmentation import (
            audience_target_for_user,
            audience_target_user_id,
        )

        target = audience_target_for_user(4242)

        self.assertEqual(target, "user:4242")
        self.assertEqual(audience_target_user_id(target), 4242)
        self.assertEqual(audience_target_user_id("USER:4242"), 4242)

    def test_an_email_only_user_target_round_trips(self) -> None:
        from bot.services.audience_segmentation import (
            audience_target_for_user,
            audience_target_user_id,
        )

        target = audience_target_for_user(-1351969585506524)

        self.assertEqual(target, "user:-1351969585506524")
        self.assertEqual(audience_target_user_id(target), -1351969585506524)

    def test_only_a_numeric_single_user_target_is_recognized(self) -> None:
        from bot.services.audience_segmentation import audience_target_user_id

        for value in ("all", "user:", "user:abc", "user:12x", "users:12", "", "user:--1"):
            with self.subTest(value=value):
                self.assertIsNone(audience_target_user_id(value))

    def test_the_single_user_prefix_is_reserved_from_plugins(self) -> None:
        from bot.services.audience_segmentation import AUDIENCE_USER_PREFIX

        self.assertEqual(AUDIENCE_USER_PREFIX, "user:")


class TariffAudienceTests(unittest.TestCase):
    def test_a_tariff_target_round_trips(self) -> None:
        from bot.services.audience_segmentation import (
            audience_target_for_tariff,
            audience_target_tariff_key,
        )

        target = audience_target_for_tariff("Pro-Plus")

        self.assertEqual(target, "tariff:pro-plus")
        self.assertEqual(audience_target_tariff_key(target), "pro-plus")
        self.assertEqual(audience_target_tariff_key("TARIFF:pro-plus"), "pro-plus")

    def test_only_a_well_formed_tariff_target_is_recognized(self) -> None:
        from bot.services.audience_segmentation import audience_target_tariff_key

        for value in ("all", "tariff:", "tariffs:x", "tariff:with space", ""):
            with self.subTest(value=value):
                self.assertIsNone(audience_target_tariff_key(value))

    def test_offered_tariffs_become_grouped_audiences(self) -> None:
        from sqlalchemy.orm import sessionmaker

        from bot.services.audience_segmentation import AudienceSegmentationService

        service = AudienceSegmentationService(
            cast(sessionmaker, None),
            tariffs=[("basic", "Basic"), ("pro", "Pro")],
        )
        definitions = service.audiences()

        self.assertEqual(
            [definition.target for definition in definitions],
            ["tariff:basic", "tariff:pro"],
        )
        self.assertEqual({definition.icon for definition in definitions}, {"tag"})
        self.assertEqual(
            {definition.group_label_key for definition in definitions},
            {"broadcast_audience_group_tariffs"},
        )
        # A tariff nobody offers is not addressable, so a stale draft cannot
        # silently resolve to an empty audience.
        self.assertTrue(service.has_target("tariff:pro"))
        self.assertFalse(service.has_target("tariff:legacy"))

    def test_the_tariff_prefix_is_reserved_from_plugins(self) -> None:
        from sqlalchemy.orm import sessionmaker

        from bot.services.audience_segmentation import (
            AudienceProvider,
            AudienceSegmentationService,
        )

        async def resolve() -> list[int]:
            return []

        service = AudienceSegmentationService(cast(sessionmaker, None))
        with self.assertRaisesRegex(ValueError, "reserved by core"):
            service.register_provider(
                AudienceProvider(
                    target="tariff:pro",
                    label_key="x",
                    fallback_label="X",
                    resolve_user_ids=resolve,
                )
            )


class MessageButtonLanguageTests(unittest.TestCase):
    """A button reaches a customer, so its caption follows their language."""

    LOCALES: ClassVar[dict[str, dict[str, str]]] = {
        "ru": {"message_button_plans": "Открыть тарифы", "message_button_promo": "Промокод"},
        "en": {"message_button_plans": "Open plans", "message_button_promo": "Promo code"},
        "de": {"message_button_plans": "Tarife ansehen", "message_button_promo": "Gutschein"},
    }

    def _translate(self, language: str | None, key: str) -> str:
        return self.LOCALES.get(str(language or "en"), {}).get(key, "")

    def test_a_button_without_an_authored_caption_speaks_the_recipients_language(self) -> None:
        button = MessageButtonInput(kind="webapp_section", section="plans")

        for language, expected in (
            ("ru", "Открыть тарифы"),
            ("en", "Open plans"),
            ("de", "Tarife ansehen"),
        ):
            with self.subTest(language=language):
                resolved = resolve_message_buttons(
                    [cast(Any, button)],
                    mini_app_url=MINI_APP_HTTPS,
                    bot_username="shop_bot",
                    language=language,
                    translate=self._translate,
                )
                self.assertEqual(resolved[0].label, expected)

    def test_a_language_nobody_prepared_still_gets_a_caption(self) -> None:
        # Falling through to the deployment default beats an empty button.
        resolved = resolve_message_buttons(
            [cast(Any, MessageButtonInput(kind="webapp_section", section="plans"))],
            mini_app_url=MINI_APP_HTTPS,
            bot_username="shop_bot",
            language="fr",
            translate=self._translate,
            default_language="en",
        )

        self.assertEqual(resolved[0].label, "Open plans")

    def test_an_authored_caption_wins_over_the_prepared_one(self) -> None:
        button = MessageButtonInput(
            kind="webapp_section", section="plans", labels={"de": "Meine Tarife"}
        )

        resolved = resolve_message_buttons(
            [cast(Any, button)],
            mini_app_url=MINI_APP_HTTPS,
            bot_username="shop_bot",
            language="de",
            translate=self._translate,
        )

        self.assertEqual(resolved[0].label, "Meine Tarife")

    def test_one_authored_caption_covers_every_language(self) -> None:
        # An author who wrote a single caption meant it for everybody.
        button = MessageButtonInput(kind="webapp_section", section="plans", label="Shop")

        for language in ("ru", "de", "fr"):
            with self.subTest(language=language):
                resolved = resolve_message_buttons(
                    [cast(Any, button)],
                    mini_app_url=MINI_APP_HTTPS,
                    bot_username="shop_bot",
                    language=language,
                    translate=self._translate,
                )
                self.assertEqual(resolved[0].label, "Shop")

    def test_a_regional_caption_falls_back_to_its_base_language(self) -> None:
        button = MessageButtonInput(kind="webapp_section", section="plans", labels={"pt": "Planos"})

        resolved = resolve_message_buttons(
            [cast(Any, button)],
            mini_app_url=MINI_APP_HTTPS,
            bot_username="shop_bot",
            language="pt-BR",
            translate=self._translate,
        )

        self.assertEqual(resolved[0].label, "Planos")

    def test_a_caller_without_translations_still_requires_a_caption(self) -> None:
        # This is exactly how every caller behaved before prepared captions
        # existed, so adding them cannot turn an old mistake into a silent send.
        with self.assertRaises(MessageValidationError) as raised:
            resolve_message_buttons(
                [cast(Any, MessageButtonInput(kind="webapp_section", section="plans"))],
                mini_app_url=MINI_APP_HTTPS,
                bot_username="shop_bot",
            )

        self.assertEqual(raised.exception.code, "button_label_required")

    def test_every_prepared_caption_exists_in_both_base_locales(self) -> None:
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "locales"
        for language in ("ru", "en"):
            data = json.loads((root / f"{language}.json").read_text(encoding="utf-8"))
            for key in MESSAGE_BUTTON_LABEL_KEYS:
                with self.subTest(language=language, key=key):
                    self.assertTrue(str(data.get(key, "")).strip())


class LocalizedTextTests(unittest.TestCase):
    def test_the_recipients_language_wins(self) -> None:
        values = {"ru": "Привет", "en": "Hello"}

        self.assertEqual(resolve_localized_text(values, language="ru"), "Привет")
        self.assertEqual(resolve_localized_text(values, language="en"), "Hello")

    def test_an_untranslated_language_falls_back_to_the_default(self) -> None:
        values = {"ru": "Привет", "en": "Hello"}

        self.assertEqual(
            resolve_localized_text(values, language="fr", default_language="en"), "Hello"
        )

    def test_a_customer_is_never_left_with_nothing(self) -> None:
        self.assertEqual(
            resolve_localized_text({"de": "Hallo"}, language="fr", default_language="en"), "Hallo"
        )
        self.assertEqual(resolve_localized_text({}, language="fr"), "")

    def test_blank_variants_are_not_written_languages(self) -> None:
        # An empty tab in the editor means "not written yet", not "send empty".
        self.assertEqual(
            resolve_localized_text({"ru": "   ", "en": "Hello"}, language="ru"), "Hello"
        )
