from __future__ import annotations

import html
from typing import TYPE_CHECKING, Optional, Protocol

if TYPE_CHECKING:
    from bot.middlewares.i18n import JsonI18n
    from config.settings import Settings

from .email_templates_common import (
    _BG,
    _BORDER,
    _TEXT,
    _TEXT_DIM,
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
    _telegram_html_to_email_html,
    _telegram_html_to_text,
    _theme_accent,
)


class _GettextProvider(Protocol):
    def gettext(self, lang_code: Optional[str], key: str, **kwargs: object) -> str: ...


def render_user_notification(
    settings: Settings,
    *,
    language_code: Optional[str],
    subject: str,
    message_text: str,
    dashboard_url: Optional[str] = None,
    cta_label: Optional[str] = None,
    heading: Optional[str] = None,
    intro: Optional[str] = None,
    i18n: Optional[JsonI18n] = None,
) -> EmailContent:
    i18n = _resolve_i18n(i18n)
    lang = _normalize_lang(language_code, settings)
    accent = _theme_accent(settings)
    brand = _brand_title(settings)
    safe_dashboard_url = (dashboard_url or "").strip()
    final_subject = (subject or "").strip() or _t_text(
        i18n, lang, "email_user_notification_subject"
    )
    final_heading = (heading or "").strip() or final_subject
    final_intro = (intro or "").strip() or _t_text(i18n, lang, "email_user_notification_intro")
    final_cta_label = (cta_label or "").strip() or _t_text(
        i18n,
        lang,
        "email_user_notification_cta",
    )
    footer = _t_html(i18n, lang, "email_footer_auto", brand=brand)
    message_html = (
        f'<div style="margin:0 0 16px 0;background:{_BG};border:1px solid {_BORDER};'
        f"border-radius:14px;padding:14px 16px;font-size:14px;line-height:1.55;color:{_TEXT};"
        f'white-space:pre-wrap;">{_telegram_html_to_email_html(message_text)}</div>'
    )
    body_parts = [message_html]
    if safe_dashboard_url:
        body_parts.append(
            _cta_button_html(label=final_cta_label, url=safe_dashboard_url, accent=accent)
        )

    rendered = _layout(
        settings=settings,
        language_code=lang,
        preheader=final_subject,
        heading=final_heading,
        intro_html=html.escape(final_intro),
        body_html="".join(body_parts),
        footer_html=footer,
        accent=accent,
    )
    text_lines = [final_subject, "", _telegram_html_to_text(message_text)]
    if safe_dashboard_url:
        text_lines.extend(
            [
                "",
                _t_text(
                    i18n, lang, "email_user_notification_text_dashboard", url=safe_dashboard_url
                ),
            ]
        )
    return _email_content(subject=final_subject, text="\n".join(text_lines), layout=rendered)


def render_subscription_expiring(
    settings: Settings,
    *,
    language_code: Optional[str],
    days_left: int,
    end_date_text: str,
    dashboard_url: Optional[str],
    i18n: Optional[JsonI18n] = None,
) -> EmailContent:
    i18n = _resolve_i18n(i18n)
    lang = _normalize_lang(language_code, settings)
    accent = _theme_accent(settings)
    brand = _brand_title(settings)
    safe_dashboard_url = (dashboard_url or "").strip()
    days = max(0, int(days_left))
    end_date = end_date_text or "—"

    if days == 0:
        suffix = "today"
    elif days == 1:
        suffix = "tomorrow"
    else:
        suffix = "days"

    subject = _t_text(i18n, lang, f"email_subscription_expiring_subject_{suffix}", days=days)
    heading = _t_text(i18n, lang, f"email_subscription_expiring_heading_{suffix}", days=days)
    preheader = _t_text(i18n, lang, f"email_subscription_expiring_preheader_{suffix}", days=days)
    intro = _t_text(i18n, lang, f"email_subscription_expiring_intro_{suffix}", days=days)
    note = _t_text(i18n, lang, "email_subscription_expiring_note")
    footer = _t_html(i18n, lang, "email_footer_auto", brand=brand)
    cta_label = _t_text(i18n, lang, "email_subscription_expiring_cta")

    rows = [
        (_t_text(i18n, lang, "email_subscription_expiring_row_days_left"), str(days)),
        (_t_text(i18n, lang, "email_subscription_expiring_row_end_date"), end_date),
    ]

    text_lines = [
        _t_text(i18n, lang, "email_subscription_expiring_text", heading=heading, end_date=end_date),
    ]
    if safe_dashboard_url:
        text_lines.append(
            _t_text(i18n, lang, "email_subscription_expiring_text_renew", url=safe_dashboard_url)
        )

    body_parts = [_info_rows_html(rows)]
    if safe_dashboard_url:
        body_parts.append(_cta_button_html(label=cta_label, url=safe_dashboard_url, accent=accent))
    body_parts.append(
        f'<p style="margin:6px 0 0 0;font-size:12px;line-height:1.55;color:{_TEXT_DIM};">{html.escape(note)}</p>'  # noqa: E501
    )

    rendered = _layout(
        settings=settings,
        language_code=lang,
        preheader=preheader,
        heading=heading,
        intro_html=html.escape(intro),
        body_html="".join(body_parts),
        footer_html=footer,
        accent=accent,
    )
    return _email_content(subject=subject, text="\n".join(text_lines), layout=rendered)


def _lifecycle_text(i18n: _GettextProvider, lang: str, key: str, **kwargs: object) -> str:
    return i18n.gettext(lang, key, **kwargs)


def _subscription_lifecycle_title(
    i18n: _GettextProvider,
    lang: str,
    notification_key: str,
    *,
    days_left: Optional[int],
    hours_before: Optional[int],
) -> str:
    if notification_key == "before_2d_autorenew":
        return _lifecycle_text(i18n, lang, "email_subscription_lifecycle_subject_autorenew")
    if notification_key == "expired":
        return _lifecycle_text(i18n, lang, "email_subscription_lifecycle_subject_expired")
    if notification_key == "expired_24h_after":
        return _lifecycle_text(i18n, lang, "email_subscription_lifecycle_subject_expired_after")
    if hours_before is not None:
        return _lifecycle_text(
            i18n,
            lang,
            "email_subscription_lifecycle_subject_before_hours",
            hours=hours_before,
        )
    return _lifecycle_text(
        i18n,
        lang,
        "email_subscription_lifecycle_subject_before_days",
        days=max(0, int(days_left or 0)),
    )


def render_subscription_lifecycle_notification(
    settings: Settings,
    *,
    language_code: Optional[str],
    notification_key: str,
    message_text: str,
    end_date_text: str,
    dashboard_url: Optional[str],
    mirrored_from_telegram: bool = False,
    days_left: Optional[int] = None,
    hours_before: Optional[int] = None,
    i18n: Optional[JsonI18n] = None,
) -> EmailContent:
    i18n = _resolve_i18n(i18n)
    lang = _normalize_lang(language_code, settings)
    accent = _theme_accent(settings)
    brand = _brand_title(settings)
    safe_dashboard_url = (dashboard_url or "").strip()
    end_date = end_date_text or "—"
    subject = _subscription_lifecycle_title(
        i18n,
        lang,
        notification_key,
        days_left=days_left,
        hours_before=hours_before,
    )
    intro_key = (
        "email_subscription_lifecycle_intro_mirrored"
        if mirrored_from_telegram
        else "email_subscription_lifecycle_intro_direct"
    )
    intro = _t_text(i18n, lang, intro_key)
    footer = _t_html(i18n, lang, "email_footer_auto", brand=brand)
    cta_label = _t_text(i18n, lang, "email_subscription_lifecycle_cta")

    rows = [
        (_t_text(i18n, lang, "email_subscription_lifecycle_row_end_date"), end_date),
    ]
    message_html = (
        f'<div style="margin:0 0 16px 0;background:{_BG};border:1px solid {_BORDER};'
        f"border-radius:14px;padding:14px 16px;font-size:14px;line-height:1.55;color:{_TEXT};"
        f'white-space:pre-wrap;">{html.escape(message_text or "")}</div>'
    )
    body_parts = [_info_rows_html(rows), message_html]
    if safe_dashboard_url:
        body_parts.append(_cta_button_html(label=cta_label, url=safe_dashboard_url, accent=accent))

    rendered = _layout(
        settings=settings,
        language_code=lang,
        preheader=subject,
        heading=subject,
        intro_html=html.escape(intro),
        body_html="".join(body_parts),
        footer_html=footer,
        accent=accent,
    )

    text_lines = [subject, "", message_text]
    if safe_dashboard_url:
        text_lines.extend(
            [
                "",
                _t_text(
                    i18n,
                    lang,
                    "email_subscription_lifecycle_text_renew",
                    url=safe_dashboard_url,
                ),
            ]
        )
    return _email_content(subject=subject, text="\n".join(text_lines), layout=rendered)
