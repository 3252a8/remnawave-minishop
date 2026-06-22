from __future__ import annotations

import html
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from bot.middlewares.i18n import JsonI18n
    from config.settings import Settings

from .email_templates_common import (
    _BG,
    _BORDER,
    _TEXT_DIM,
    _TEXT_MUTED,
    EmailContent,
    _brand_title,
    _cta_button_html,
    _email_content,
    _format_minutes,
    _info_rows_html,
    _layout,
    _normalize_lang,
    _resolve_i18n,
    _t_html,
    _t_text,
    _theme_accent,
)


def render_login_code(
    settings: Settings,
    *,
    code: str,
    language_code: Optional[str],
    magic_link: Optional[str] = None,
    purpose: str = "login",
    i18n: Optional[JsonI18n] = None,
) -> EmailContent:
    i18n = _resolve_i18n(i18n)
    lang = _normalize_lang(language_code, settings)
    minutes = _format_minutes(settings.EMAIL_CODE_TTL_SECONDS)
    accent = _theme_accent(settings)
    brand = _brand_title(settings)
    template_prefix = "email_set_password_code" if purpose == "set_password" else "email_login_code"
    safe_magic_link = (magic_link or "").strip() if template_prefix == "email_login_code" else ""

    subject = _t_text(i18n, lang, f"{template_prefix}_subject", code=code)
    preheader = _t_text(i18n, lang, f"{template_prefix}_preheader", minutes=minutes)
    heading = _t_text(i18n, lang, f"{template_prefix}_heading")
    intro = _t_text(i18n, lang, f"{template_prefix}_intro")
    expiry_html = _t_html(i18n, lang, f"{template_prefix}_expiry_html", minutes=minutes)
    security = _t_text(i18n, lang, f"{template_prefix}_security")
    footer = _t_html(i18n, lang, "email_footer_auto", brand=brand)
    text_lines = [_t_text(i18n, lang, f"{template_prefix}_text", code=code, minutes=minutes)]
    if safe_magic_link:
        text_lines.append(_t_text(i18n, lang, "email_login_code_text_magic", url=safe_magic_link))

    code_block = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 18px 0;">'  # noqa: E501
        f'<tr><td align="center" style="background:{_BG};border:1px solid {_BORDER};border-radius:14px;padding:22px 16px;">'  # noqa: E501
        f"<div style=\"font-family:'JetBrains Mono','SFMono-Regular',Menlo,Consolas,monospace;font-size:36px;line-height:1;font-weight:700;letter-spacing:10px;color:{accent};\">"  # noqa: E501
        f"{html.escape(code)}"
        f"</div></td></tr></table>"
    )

    magic_block = ""
    if safe_magic_link:
        cta_label = _t_text(i18n, lang, "email_login_code_magic_cta")
        divider_label = _t_text(i18n, lang, "email_login_code_magic_or")
        magic_intro = _t_text(i18n, lang, "email_login_code_magic_intro")
        magic_hint = _t_text(i18n, lang, "email_login_code_magic_hint")
        divider_html = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:4px 0 14px 0;">'  # noqa: E501
            f"<tr>"
            f'<td width="40%" style="border-bottom:1px solid {_BORDER};font-size:0;line-height:0;">&nbsp;</td>'  # noqa: E501
            f'<td align="center" style="padding:0 10px;font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:{_TEXT_DIM};white-space:nowrap;">{html.escape(divider_label)}</td>'  # noqa: E501
            f'<td width="40%" style="border-bottom:1px solid {_BORDER};font-size:0;line-height:0;">&nbsp;</td>'  # noqa: E501
            f"</tr></table>"
        )
        magic_block = (
            divider_html
            + f'<p style="margin:0 0 4px 0;font-size:13px;line-height:1.55;color:{_TEXT_MUTED};text-align:center;">{html.escape(magic_intro)}</p>'  # noqa: E501
            + _cta_button_html(label=cta_label, url=safe_magic_link, accent=accent)
            + f'<p style="margin:0 0 6px 0;font-size:12px;line-height:1.55;color:{_TEXT_DIM};text-align:center;">{html.escape(magic_hint)}</p>'  # noqa: E501
        )

    body_html = (
        code_block
        + f'<p style="margin:0 0 8px 0;font-size:13px;line-height:1.55;color:{_TEXT_MUTED};">{expiry_html}</p>'  # noqa: E501
        + f'<p style="margin:0 0 4px 0;font-size:12px;line-height:1.55;color:{_TEXT_DIM};">{html.escape(security)}</p>'  # noqa: E501
        + magic_block
    )

    rendered = _layout(
        settings=settings,
        language_code=lang,
        preheader=preheader,
        heading=heading,
        intro_html=html.escape(intro),
        body_html=body_html,
        footer_html=footer,
        accent=accent,
    )
    return _email_content(subject=subject, text="\n".join(text_lines), layout=rendered)


def render_account_merged(
    settings: Settings,
    *,
    language_code: Optional[str],
    primary_user_id: Optional[int],
    removed_user_id: Optional[int],
    final_end_date_text: str,
    i18n: Optional[JsonI18n] = None,
) -> EmailContent:
    i18n = _resolve_i18n(i18n)
    lang = _normalize_lang(language_code, settings)
    brand = _brand_title(settings)
    primary = "—" if primary_user_id is None else f"#{primary_user_id}"
    removed = "—" if removed_user_id is None else f"#{removed_user_id}"
    end_date = final_end_date_text or "—"

    subject = _t_text(i18n, lang, "email_account_merged_subject")
    preheader = _t_text(i18n, lang, "email_account_merged_preheader")
    heading = _t_text(i18n, lang, "email_account_merged_heading")
    intro = _t_text(i18n, lang, "email_account_merged_intro")
    note = _t_text(i18n, lang, "email_account_merged_note")
    footer = _t_html(i18n, lang, "email_footer_auto", brand=brand)
    text = _t_text(
        i18n,
        lang,
        "email_account_merged_text",
        primary=primary,
        removed=removed,
        end_date=end_date,
    )

    rows = [
        (_t_text(i18n, lang, "email_account_merged_row_kept"), primary),
        (_t_text(i18n, lang, "email_account_merged_row_removed"), removed),
        (_t_text(i18n, lang, "email_account_merged_row_end_date"), end_date),
    ]
    body_html = (
        _info_rows_html(rows)
        + f'<p style="margin:0;font-size:12px;line-height:1.55;color:{_TEXT_DIM};">{html.escape(note)}</p>'  # noqa: E501
    )

    rendered = _layout(
        settings=settings,
        language_code=lang,
        preheader=preheader,
        heading=heading,
        intro_html=html.escape(intro),
        body_html=body_html,
        footer_html=footer,
    )
    return _email_content(subject=subject, text=text, layout=rendered)
