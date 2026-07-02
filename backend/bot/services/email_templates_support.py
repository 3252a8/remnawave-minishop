from __future__ import annotations

import html
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.middlewares.i18n import JsonI18n
    from config.settings import Settings

from .email_templates_common import (
    _BG,
    _BORDER,
    _TEXT,
    EmailContent,
    _brand_title,
    _cta_button_html,
    _email_content,
    _info_rows_html,
    _layout,
    _normalize_lang,
    _resolve_i18n,
    _t_html,
    _t_text,
    _theme_accent,
)


def _support_email(
    settings: Settings,
    i18n: JsonI18n | None,
    language: str | None,
    *,
    subject: str,
    heading: str,
    intro: str,
    rows: Sequence[tuple[str, str]],
    body_preview: str,
    ticket_url: str | None,
    cta_label: str,
) -> EmailContent:
    i18n = _resolve_i18n(i18n)
    lang = _normalize_lang(language, settings)
    brand = _brand_title(settings)
    accent = _theme_accent(settings)
    safe_url = (ticket_url or "").strip()
    footer = _t_html(i18n, lang, "email_footer_auto", brand=brand)
    localized_rows = [
        (_t_text(i18n, lang, label) if str(label).startswith("email_") else str(label), value)
        for label, value in rows
    ]
    preview_block = (
        f'<div style="margin:0 0 16px 0;background:{_BG};border:1px solid {_BORDER};'
        f"border-radius:14px;padding:14px 16px;font-size:14px;line-height:1.55;color:{_TEXT};"
        f'white-space:pre-wrap;">{html.escape(body_preview or "")}</div>'
    )
    body_parts = [_info_rows_html(localized_rows), preview_block]
    if safe_url:
        body_parts.append(_cta_button_html(label=cta_label, url=safe_url, accent=accent))
    rendered = _layout(
        settings=settings,
        language_code=lang,
        preheader=intro,
        heading=heading,
        intro_html=html.escape(intro),
        body_html="".join(body_parts),
        footer_html=footer,
        accent=accent,
    )
    text_lines = [
        intro,
        "",
        *[f"{label}: {value}" for label, value in localized_rows],
        "",
        body_preview,
    ]
    if safe_url:
        text_lines.extend(["", safe_url])
    return _email_content(subject=subject, text="\n".join(text_lines), layout=rendered)


def render_support_new_ticket_admin(
    settings: Settings,
    i18n: JsonI18n | None,
    language: str | None,
    *,
    ticket_id: int,
    user_display: str,
    subject: str,
    body_preview: str,
    snapshot_rows: Sequence[tuple[str, str]],
    ticket_url: str | None,
) -> EmailContent:
    i18n = _resolve_i18n(i18n)
    lang = _normalize_lang(language, settings)
    rows = [
        ("email_support_row_ticket", f"#{ticket_id}"),
        ("email_support_row_user", user_display),
        ("email_support_row_subject", subject),
        *snapshot_rows,
    ]
    return _support_email(
        settings,
        i18n,
        lang,
        subject=_t_text(i18n, lang, "email_support_new_ticket_admin_subject", ticket_id=ticket_id),
        heading=_t_text(i18n, lang, "email_support_new_ticket_admin_heading", ticket_id=ticket_id),
        intro=_t_text(i18n, lang, "email_support_new_ticket_admin_intro"),
        rows=rows,
        body_preview=body_preview,
        ticket_url=ticket_url,
        cta_label=_t_text(i18n, lang, "email_support_cta_open_ticket"),
    )


def render_support_user_reply_admin(
    settings: Settings,
    i18n: JsonI18n | None,
    language: str | None,
    *,
    ticket_id: int,
    user_display: str,
    subject: str,
    body_preview: str,
    snapshot_rows: Sequence[tuple[str, str]],
    ticket_url: str | None,
) -> EmailContent:
    i18n = _resolve_i18n(i18n)
    lang = _normalize_lang(language, settings)
    rows = [
        ("email_support_row_ticket", f"#{ticket_id}"),
        ("email_support_row_user", user_display),
        ("email_support_row_subject", subject),
        *snapshot_rows,
    ]
    return _support_email(
        settings,
        i18n,
        lang,
        subject=_t_text(i18n, lang, "email_support_user_reply_admin_subject", ticket_id=ticket_id),
        heading=_t_text(i18n, lang, "email_support_user_reply_admin_heading", ticket_id=ticket_id),
        intro=_t_text(i18n, lang, "email_support_user_reply_admin_intro"),
        rows=rows,
        body_preview=body_preview,
        ticket_url=ticket_url,
        cta_label=_t_text(i18n, lang, "email_support_cta_open_ticket"),
    )


def render_support_admin_reply_user(
    settings: Settings,
    i18n: JsonI18n | None,
    language: str | None,
    *,
    ticket_id: int,
    subject: str,
    body_preview: str,
    ticket_url: str | None,
) -> EmailContent:
    i18n = _resolve_i18n(i18n)
    lang = _normalize_lang(language, settings)
    return _support_email(
        settings,
        i18n,
        lang,
        subject=_t_text(i18n, lang, "email_support_admin_reply_user_subject", ticket_id=ticket_id),
        heading=_t_text(i18n, lang, "email_support_admin_reply_user_heading", ticket_id=ticket_id),
        intro=_t_text(i18n, lang, "email_support_admin_reply_user_intro"),
        rows=[
            ("email_support_row_ticket", f"#{ticket_id}"),
            ("email_support_row_subject", subject),
        ],
        body_preview=body_preview,
        ticket_url=ticket_url,
        cta_label=_t_text(i18n, lang, "email_support_cta_open_mini_app"),
    )


def render_support_ticket_closed_user(
    settings: Settings,
    i18n: JsonI18n | None,
    language: str | None,
    *,
    ticket_id: int,
    subject: str,
    body_preview: str = "",
    ticket_url: str | None,
) -> EmailContent:
    i18n = _resolve_i18n(i18n)
    lang = _normalize_lang(language, settings)
    return _support_email(
        settings,
        i18n,
        lang,
        subject=_t_text(
            i18n, lang, "email_support_ticket_closed_user_subject", ticket_id=ticket_id
        ),
        heading=_t_text(
            i18n, lang, "email_support_ticket_closed_user_heading", ticket_id=ticket_id
        ),
        intro=_t_text(i18n, lang, "email_support_ticket_closed_user_intro"),
        rows=[
            ("email_support_row_ticket", f"#{ticket_id}"),
            ("email_support_row_subject", subject),
        ],
        body_preview=body_preview or _t_text(i18n, lang, "email_support_ticket_closed_user_body"),
        ticket_url=ticket_url,
        cta_label=_t_text(i18n, lang, "email_support_cta_open_mini_app"),
    )
