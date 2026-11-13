from bot.app.web.admin_settings_manifest_types import SettingField

TELEGRAM_CHAT_MENU_FIELDS = (
    SettingField(
        "TELEGRAM_CHAT_MENU_MODE",
        "string",
        "general",
        "Telegram chat menu button",
        "Choose the button beside the message input. In the Mini App mode, enter a label and URL.",
        optional=False,
        choices=(
            ("keep", "Do not change (BotFather)"),
            ("web_app", "Open Mini App"),
            ("commands", "Show command list"),
        ),
        subsection="telegram",
    ),
    SettingField(
        "TELEGRAM_CHAT_MENU_TEXT",
        "string",
        "general",
        "Mini App button label",
        subsection="telegram",
    ),
    SettingField(
        "TELEGRAM_CHAT_MENU_URL",
        "url",
        "general",
        "Mini App button HTTPS URL",
        subsection="telegram",
    ),
)
