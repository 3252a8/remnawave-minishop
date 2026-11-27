from functools import lru_cache
from pathlib import Path

from bot.middlewares.i18n import JsonI18n
from bot.plugins.spec import PluginContext


@lru_cache(maxsize=1)
def _bundled_catalog() -> JsonI18n:
    return JsonI18n(str(Path(__file__).parent / "locales"), default="en")


def plugin_i18n(ctx: PluginContext) -> JsonI18n:
    return ctx.i18n or _bundled_catalog()
