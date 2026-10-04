"""One cosmetic resolver shared by the delivered keyboard and the admin preview."""

from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.custom_emoji import split_decorative_emoji
from config.settings import Settings
from config.telegram_menu import ButtonAppearance, TelegramMenuAppearance, parse_menu_appearance


@dataclass(frozen=True)
class MenuButton:
    id: str
    button: InlineKeyboardButton


def menu_button(identifier: str, **kwargs: object) -> MenuButton:
    return MenuButton(identifier, InlineKeyboardButton.model_validate(kwargs))


def styled_button(
    button: InlineKeyboardButton, appearance: ButtonAppearance
) -> InlineKeyboardButton:
    emoji, label = split_decorative_emoji(button.text)
    update: dict[str, object] = {
        "style": None if appearance.style == "default" else appearance.style,
        "icon_custom_emoji_id": None,
    }
    if appearance.icon_mode == "none":
        update["text"] = label
    elif appearance.icon_mode == "custom":
        update["text"] = label if emoji else button.text
        update["icon_custom_emoji_id"] = appearance.icon_custom_emoji_id
    return button.model_copy(update=update)


class MenuKeyboardBuilder:
    def __init__(
        self, settings: Settings | None, button_ids: list[list[str]] | None = None
    ) -> None:
        self.appearance = (
            parse_menu_appearance(settings.TELEGRAM_MENU_APPEARANCE_JSON)
            if settings is not None
            else TelegramMenuAppearance()
        )
        self.builder = InlineKeyboardBuilder()
        self.button_ids = button_ids

    def row(self, *buttons: MenuButton) -> None:
        self.builder.row(
            *[
                styled_button(item.button, self.appearance.buttons.get(item.id, ButtonAppearance()))
                for item in buttons
            ]
        )
        if self.button_ids is not None:
            self.button_ids.append([item.id for item in buttons])

    def as_markup(self) -> InlineKeyboardMarkup:
        return self.builder.as_markup()
