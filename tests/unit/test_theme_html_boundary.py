from types import SimpleNamespace

from bot.app.web.webapp.assets_theme import (
    _app_deeplink_theme_head_markup,
    _initial_theme_head_markup,
)
from config.webapp_themes_config import builtin_webapp_themes_config


def test_legacy_theme_tokens_cannot_close_an_inline_style() -> None:
    catalog = builtin_webapp_themes_config("#abcdef")
    theme = catalog.themes[0]
    # Assignment intentionally simulates an already installed legacy descriptor.
    theme.tokens.bg = '</style><meta http-equiv="refresh" content="0;url=/evil">'
    theme.tokens.separator = "< >"
    request = SimpleNamespace(get=lambda key, default="": "nonce")
    for markup in (
        _initial_theme_head_markup(request, theme, "#abcdef"),
        _app_deeplink_theme_head_markup(request, theme, catalog, "#abcdef"),
    ):
        assert markup.count("</style>") == 1
        assert "<meta" not in markup
        assert "\\3c " in markup
        assert '--separator:"\\3c  \\3e "' in markup
