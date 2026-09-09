"""Branded gift delivery message, shared by the outbox and visual previews."""

import html

from bot.middlewares.i18n import JsonI18n
from bot.services.email_templates_common import (
    EmailContent,
    _cta_button_html,
    _email_content,
    _layout,
    _theme_accent,
)
from config.settings import Settings


def render_gift_email(
    settings: Settings,
    i18n: JsonI18n,
    *,
    language: str,
    link: str,
) -> EmailContent:
    title = i18n.gettext(language, "wa_gift_received_title")
    intro = i18n.gettext(language, "email_gift_intro")
    note = i18n.gettext(language, "wa_gift_link_private")
    return _email_content(
        subject=title,
        text=f"{title}\n\n{intro}\n\n{link}\n\n{note}",
        layout=_layout(
            settings=settings,
            language_code=language,
            preheader=intro,
            heading=title,
            intro_html=html.escape(intro),
            body_html=_cta_button_html(
                label=i18n.gettext(language, "wa_gift_activate"),
                url=link,
                accent=_theme_accent(settings),
            ),
            footer_html=html.escape(note),
        ),
    )
