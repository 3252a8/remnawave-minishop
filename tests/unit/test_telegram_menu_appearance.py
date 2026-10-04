from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.user_keyboards_menus import get_main_menu_inline_keyboard
from bot.middlewares.i18n import JsonI18n
from bot.services import telegram_settings_lock
from bot.services.telegram_emoji_schemas import MenuPreviewBody
from bot.services.telegram_menu_preview import preview_menu
from config.settings import Settings
from config.telegram_menu import (
    APPEARANCE_KEY,
    ButtonAppearance,
    TelegramMenuAppearance,
    emoji_source,
    parse_menu_appearance,
    telegram_setting_revision,
)


def settings(**values) -> Settings:
    return Settings(
        _env_file=None,
        BOT_TOKEN="123456789:AA_test_bot_token",
        POSTGRES_USER="test",
        POSTGRES_PASSWORD="test",
        **values,
    )


@pytest.mark.parametrize("value", ["0", "-1", "1e10", "12/3", "1" * 21, 12345678901234567890])
def test_icon_ids_are_positive_decimal_strings(value) -> None:
    with pytest.raises(ValidationError):
        ButtonAppearance(icon_custom_emoji_id=value)


def test_cosmetic_schema_rejects_navigation_and_unknown_styles() -> None:
    for button in ({"style": "#ff0000"}, {"style": "danger", "url": "https://example.com"}):
        with pytest.raises(ValidationError):
            TelegramMenuAppearance(buttons={"support": button})
    with pytest.raises(ValidationError):
        TelegramMenuAppearance(buttons={"missing_system_button": {"style": "success"}})
    identifier = "12345678901234567890"
    appearance = parse_menu_appearance(
        {"buttons": {"support": {"icon_custom_emoji_id": identifier}}}
    )
    assert appearance.buttons["support"].icon_custom_emoji_id == identifier
    assert appearance.buttons["support"].icon_mode == "custom"


def test_styles_and_custom_icons_preserve_menu_actions_and_order() -> None:
    config = settings(
        SUBSCRIPTION_MINI_APP_URL="https://app.example.com",
        SUPPORT_LINK="https://t.me/help_center",
    )
    i18n = JsonI18n(str(Path("locales")), default="en")
    before = get_main_menu_inline_keyboard("en", i18n, config, True)
    appearance = TelegramMenuAppearance(
        buttons={
            "support": ButtonAppearance(style="success", icon_custom_emoji_id="9007199254740993"),
            "personal_account": ButtonAppearance(style="primary", icon_mode="none"),
        }
    )
    config.TELEGRAM_MENU_APPEARANCE_JSON = appearance.model_dump_json()
    after = get_main_menu_inline_keyboard("en", i18n, config, True)
    assert len(after.inline_keyboard) == len(before.inline_keyboard)
    for old_row, new_row in zip(before.inline_keyboard, after.inline_keyboard, strict=True):
        for old, new in zip(old_row, new_row, strict=True):
            assert (old.callback_data, old.url, old.web_app) == (
                new.callback_data,
                new.url,
                new.web_app,
            )
    support = next(button for row in after.inline_keyboard for button in row if button.url)
    assert support.style == "success"
    assert support.icon_custom_emoji_id == "9007199254740993"
    assert not support.text.startswith("💬")
    assert "style" not in before.inline_keyboard[0][0].model_dump(exclude_none=True)


def test_preview_uses_actual_keyboard_and_does_not_save_the_draft() -> None:
    config = settings(TRIAL_ENABLED=True, SUPPORT_LINK="https://t.me/help_center")
    i18n = JsonI18n("locales", default="en")
    draft = MenuPreviewBody(
        language="en",
        scenario="active",
        appearance=TelegramMenuAppearance(buttons={"support": ButtonAppearance(style="danger")}),
    )
    preview, keyboard = preview_menu(config, i18n, draft)
    assert preview.rows[-1][0].id == "support"
    assert preview.rows[-1][0].style == keyboard.inline_keyboard[-1][0].style == "danger"
    assert any(
        button.id == "trial" and "subscription" in button.reason for button in preview.hidden
    )
    assert json.loads(config.TELEGRAM_MENU_APPEARANCE_JSON)["buttons"] == {}
    disabled, _ = preview_menu(
        settings(TELEGRAM_BOT_MENU_DISABLED=True),
        i18n,
        MenuPreviewBody(language="en", screen="bot", appearance=TelegramMenuAppearance()),
    )
    assert disabled.available is False
    assert disabled.rows == []


@pytest.mark.parametrize(
    "source",
    [
        "https://evil.example/addemoji/Example",
        "http://t.me/addemoji/Example",
        "https://t.me/addstickers/Example",
        "https://t.me/addemoji/Example?token=secret",
        "../Example",
    ],
)
def test_import_sources_cannot_choose_a_download_origin(source) -> None:
    with pytest.raises(ValueError):
        emoji_source(source)
    assert emoji_source("https://t.me/addemoji/Example") == ("set", "Example")
    assert emoji_source("9007199254740993") == ("emoji", "9007199254740993")


def test_revision_lock_covers_missing_rows_and_rejects_stale_writes(monkeypatch) -> None:
    async def run() -> None:
        session = AsyncMock(spec=AsyncSession)
        monkeypatch.setattr(
            telegram_settings_lock.app_settings_dal,
            "get_override_value",
            AsyncMock(return_value=(False, None)),
        )
        current = telegram_setting_revision(APPEARANCE_KEY, TelegramMenuAppearance())
        assert (
            await telegram_settings_lock.lock_telegram_settings(
                session, [APPEARANCE_KEY], {APPEARANCE_KEY: current}
            )
            is None
        )
        assert "pg_advisory_xact_lock" in str(session.execute.call_args.args[0])
        assert (
            await telegram_settings_lock.lock_telegram_settings(
                session, [APPEARANCE_KEY], {APPEARANCE_KEY: "0" * 64}
            )
            == APPEARANCE_KEY
        )

    asyncio.run(run())
