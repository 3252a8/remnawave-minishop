"""Branded HTML email templates that mirror the subscription Mini App look.

The web app uses a dark theme with a configurable accent colour
(`WEBAPP_PRIMARY_COLOR`) and an optional logo (`WEBAPP_LOGO_URL`). The same
accent + logo are reused here so emails feel like part of the product. All
copy goes through the shared `JsonI18n` instance so translations live in
``locales/<lang>.json`` next to the rest of the bot strings.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple
from urllib.parse import urlsplit

from bot.middlewares.i18n import JsonI18n, get_i18n_instance
from config.settings import Settings


_BG = "#05070a"
_CARD_BG = "#0e1116"
_BORDER = "#1a1f27"
_TEXT = "#e6e9ef"
_TEXT_MUTED = "#9aa3b2"
_TEXT_DIM = "#5d6573"
_DEFAULT_ACCENT = "#00fe7a"
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


@dataclass(frozen=True)
class EmailContent:
    subject: str
    text: str
    html: str


def _safe_color(value: Optional[str]) -> str:
    if not value:
        return _DEFAULT_ACCENT
    candidate = value.strip()
    if _HEX_RE.match(candidate):
        return candidate
    return _DEFAULT_ACCENT


def _public_logo_url(settings: Settings) -> Optional[str]:
    """Email recipients can't reach the in-app /webapp-logo proxy, so the
    raw https URL from the env is used directly. Anything else is dropped."""
    raw = (settings.WEBAPP_LOGO_URL or "").strip()
    if not raw:
        return None
    parsed = urlsplit(raw)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    return raw


def _brand_title(settings: Settings) -> str:
    title = (settings.WEBAPP_TITLE or "").strip()
    return title or "Subscription"


def _normalize_lang(language_code: Optional[str], settings: Settings) -> str:
    return (language_code or settings.DEFAULT_LANGUAGE or "ru").split("-")[0]


def _resolve_i18n(i18n: Optional[JsonI18n]) -> JsonI18n:
    return i18n or get_i18n_instance()


def _t_html(i18n: JsonI18n, lang: str, key: str, **kwargs) -> str:
    """Translate for HTML context: format args are HTML-escaped, the
    translated template itself is treated as already-safe HTML (locale files
    are author-controlled and may include simple inline tags like <strong>)."""
    safe_kwargs = {k: html.escape(str(v)) for k, v in kwargs.items()}
    return i18n.gettext(lang, key, **safe_kwargs)


def _t_text(i18n: JsonI18n, lang: str, key: str, **kwargs) -> str:
    return i18n.gettext(lang, key, **kwargs)


def _layout(
    *,
    settings: Settings,
    preheader: str,
    heading: str,
    intro_html: str,
    body_html: str,
    footer_html: str,
) -> str:
    accent = _safe_color(settings.WEBAPP_PRIMARY_COLOR)
    brand_title = html.escape(_brand_title(settings))
    logo_url = _public_logo_url(settings)
    logo_block = ""
    if logo_url:
        logo_block = (
            f'<img src="{html.escape(logo_url, quote=True)}" width="64" height="64" '
            f'alt="" style="display:block;border:0;outline:none;text-decoration:none;'
            f'border-radius:16px;">'
        )

    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="supported-color-schemes" content="dark">
<title>{html.escape(heading)}</title>
</head>
<body style="margin:0;padding:0;background:{_BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:{_TEXT};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;mso-hide:all;">{html.escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_BG};">
  <tr>
    <td align="center" style="padding:32px 16px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:480px;">
        <tr>
          <td align="center" style="padding-bottom:24px;">
            {logo_block}
            <div style="margin-top:14px;font-family:'JetBrains Mono','SFMono-Regular',Menlo,Consolas,monospace;font-weight:800;font-size:22px;line-height:1.05;color:{accent};letter-spacing:0;">{brand_title}</div>
          </td>
        </tr>
        <tr>
          <td style="background:{_CARD_BG};border:1px solid {_BORDER};border-radius:18px;padding:28px;">
            <h1 style="margin:0 0 10px 0;font-size:20px;line-height:1.25;font-weight:700;color:#ffffff;">{html.escape(heading)}</h1>
            <div style="margin:0 0 20px 0;font-size:14px;line-height:1.55;color:{_TEXT_MUTED};">{intro_html}</div>
            {body_html}
          </td>
        </tr>
        <tr>
          <td align="center" style="padding-top:20px;">
            <div style="font-size:11px;line-height:1.55;color:{_TEXT_DIM};">{footer_html}</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>
"""


def _info_rows_html(rows: Sequence[Tuple[str, str]]) -> str:
    if not rows:
        return ""
    last = len(rows) - 1
    cells = []
    for index, (label, value) in enumerate(rows):
        border = "" if index == last else f"border-bottom:1px solid {_BORDER};"
        cells.append(
            f'<tr>'
            f'<td style="padding:11px 0;{border}font-size:12px;color:{_TEXT_DIM};text-transform:uppercase;letter-spacing:0.04em;">{html.escape(label)}</td>'
            f'<td align="right" style="padding:11px 0;{border}font-family:\'JetBrains Mono\',\'SFMono-Regular\',Menlo,Consolas,monospace;font-size:14px;font-weight:600;color:{_TEXT};">{html.escape(value)}</td>'
            f'</tr>'
        )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:0 0 16px 0;background:{_BG};border:1px solid {_BORDER};border-radius:14px;padding:6px 16px;">'
        + "".join(cells)
        + "</table>"
    )


def _cta_button_html(*, label: str, url: str, accent: str) -> str:
    safe_label = html.escape(label)
    safe_url = html.escape(url, quote=True)
    # Accent green is light, so contrast text is dark; works for the default and similar light accents.
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="width:100%;margin:22px 0 18px 0;">'
        f'<tr><td align="center" bgcolor="{accent}" style="background:{accent};border-radius:12px;">'
        f'<a href="{safe_url}" target="_blank" rel="noopener" '
        f'style="display:block;width:100%;box-sizing:border-box;padding:15px 22px;'
        f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;'
        f'font-size:15px;font-weight:700;color:#05070a;text-decoration:none;letter-spacing:0.02em;text-align:center;">{safe_label}</a>'
        f'</td></tr></table>'
    )


def _format_amount(amount: float, currency: str) -> str:
    rounded = round(float(amount), 2)
    if rounded.is_integer():
        body = f"{int(rounded)}"
    else:
        body = f"{rounded:.2f}"
    suffix = (currency or "").strip()
    return f"{body} {suffix}".strip()


def _format_traffic(traffic_gb: Optional[float]) -> str:
    if traffic_gb is None:
        return "—"
    value = float(traffic_gb)
    return str(int(value)) if value.is_integer() else f"{value:g}"


def _format_minutes(seconds: int) -> int:
    return max(1, int(seconds) // 60)


def render_login_code(
    settings: Settings,
    *,
    code: str,
    language_code: Optional[str],
    magic_link: Optional[str] = None,
    i18n: Optional[JsonI18n] = None,
) -> EmailContent:
    i18n = _resolve_i18n(i18n)
    lang = _normalize_lang(language_code, settings)
    minutes = _format_minutes(settings.EMAIL_CODE_TTL_SECONDS)
    accent = _safe_color(settings.WEBAPP_PRIMARY_COLOR)
    brand = _brand_title(settings)
    safe_magic_link = (magic_link or "").strip()

    subject = _t_text(i18n, lang, "email_login_code_subject", code=code)
    preheader = _t_text(i18n, lang, "email_login_code_preheader", minutes=minutes)
    heading = _t_text(i18n, lang, "email_login_code_heading")
    intro = _t_text(i18n, lang, "email_login_code_intro")
    expiry_html = _t_html(i18n, lang, "email_login_code_expiry_html", minutes=minutes)
    security = _t_text(i18n, lang, "email_login_code_security")
    footer = _t_html(i18n, lang, "email_footer_auto", brand=brand)
    text_lines = [_t_text(i18n, lang, "email_login_code_text", code=code, minutes=minutes)]
    if safe_magic_link:
        text_lines.append(
            _t_text(i18n, lang, "email_login_code_text_magic", url=safe_magic_link)
        )

    code_block = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 18px 0;">'
        f'<tr><td align="center" style="background:{_BG};border:1px solid {_BORDER};border-radius:14px;padding:22px 16px;">'
        f'<div style="font-family:\'JetBrains Mono\',\'SFMono-Regular\',Menlo,Consolas,monospace;font-size:36px;line-height:1;font-weight:700;letter-spacing:10px;color:{accent};">'
        f'{html.escape(code)}'
        f'</div></td></tr></table>'
    )

    magic_block = ""
    if safe_magic_link:
        cta_label = _t_text(i18n, lang, "email_login_code_magic_cta")
        divider_label = _t_text(i18n, lang, "email_login_code_magic_or")
        magic_intro = _t_text(i18n, lang, "email_login_code_magic_intro")
        magic_hint = _t_text(i18n, lang, "email_login_code_magic_hint")
        divider_html = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:4px 0 14px 0;">'
            f'<tr>'
            f'<td width="40%" style="border-bottom:1px solid {_BORDER};font-size:0;line-height:0;">&nbsp;</td>'
            f'<td align="center" style="padding:0 10px;font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:{_TEXT_DIM};white-space:nowrap;">{html.escape(divider_label)}</td>'
            f'<td width="40%" style="border-bottom:1px solid {_BORDER};font-size:0;line-height:0;">&nbsp;</td>'
            f'</tr></table>'
        )
        magic_block = (
            divider_html
            + f'<p style="margin:0 0 4px 0;font-size:13px;line-height:1.55;color:{_TEXT_MUTED};text-align:center;">{html.escape(magic_intro)}</p>'
            + _cta_button_html(label=cta_label, url=safe_magic_link, accent=accent)
            + f'<p style="margin:0 0 6px 0;font-size:12px;line-height:1.55;color:{_TEXT_DIM};text-align:center;">{html.escape(magic_hint)}</p>'
        )

    body_html = (
        code_block
        + f'<p style="margin:0 0 8px 0;font-size:13px;line-height:1.55;color:{_TEXT_MUTED};">{expiry_html}</p>'
        + f'<p style="margin:0 0 4px 0;font-size:12px;line-height:1.55;color:{_TEXT_DIM};">{html.escape(security)}</p>'
        + magic_block
    )

    rendered = _layout(
        settings=settings,
        preheader=preheader,
        heading=heading,
        intro_html=html.escape(intro),
        body_html=body_html,
        footer_html=footer,
    )
    return EmailContent(subject=subject, text="\n".join(text_lines), html=rendered)


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
        + f'<p style="margin:0;font-size:12px;line-height:1.55;color:{_TEXT_DIM};">{html.escape(note)}</p>'
    )

    rendered = _layout(
        settings=settings,
        preheader=preheader,
        heading=heading,
        intro_html=html.escape(intro),
        body_html=body_html,
        footer_html=footer,
    )
    return EmailContent(subject=subject, text=text, html=rendered)


def render_payment_success(
    settings: Settings,
    *,
    language_code: Optional[str],
    sale_mode: str,
    months: int,
    traffic_gb: Optional[float],
    amount: float,
    currency: str,
    end_date_text: str,
    dashboard_url: Optional[str],
    provider_label: Optional[str] = None,
    i18n: Optional[JsonI18n] = None,
) -> EmailContent:
    i18n = _resolve_i18n(i18n)
    lang = _normalize_lang(language_code, settings)
    accent = _safe_color(settings.WEBAPP_PRIMARY_COLOR)
    brand = _brand_title(settings)
    is_traffic = sale_mode == "traffic"
    amount_text = _format_amount(amount, currency)
    safe_dashboard_url = (dashboard_url or "").strip()
    end_date = end_date_text or "—"
    traffic_label = _format_traffic(traffic_gb)

    subject = _t_text(i18n, lang, "email_payment_success_subject")
    preheader = _t_text(i18n, lang, "email_payment_success_preheader")
    heading = _t_text(i18n, lang, "email_payment_success_heading")
    footer_note = _t_text(i18n, lang, "email_payment_success_footer_note")
    footer = _t_html(i18n, lang, "email_footer_auto", brand=brand)
    cta_label = _t_text(i18n, lang, "email_payment_success_cta")

    if is_traffic:
        intro = _t_text(i18n, lang, "email_payment_success_intro_traffic", traffic_gb=traffic_label)
        period_label = _t_text(i18n, lang, "email_payment_success_row_traffic")
        period_value = _t_text(i18n, lang, "email_payment_success_traffic_value", traffic_gb=traffic_label)
        text = _t_text(
            i18n,
            lang,
            "email_payment_success_text_traffic",
            amount=amount_text,
            traffic_gb=traffic_label,
            end_date=end_date,
        )
    else:
        months_int = int(months or 0)
        intro = _t_text(i18n, lang, "email_payment_success_intro_subscription", months=months_int)
        period_label = _t_text(i18n, lang, "email_payment_success_row_period")
        period_value = _t_text(
            i18n,
            lang,
            "email_payment_success_period_value",
            months=months_int,
        )
        text = _t_text(
            i18n,
            lang,
            "email_payment_success_text_subscription",
            amount=amount_text,
            months=months_int,
            end_date=end_date,
        )

    rows: list[Tuple[str, str]] = [
        (period_label, period_value),
        (_t_text(i18n, lang, "email_payment_success_row_amount"), amount_text),
        (_t_text(i18n, lang, "email_payment_success_row_end_date"), end_date),
    ]
    if provider_label:
        rows.append((_t_text(i18n, lang, "email_payment_success_row_method"), provider_label))

    text_lines = [text]
    if safe_dashboard_url:
        text_lines.append(_t_text(i18n, lang, "email_payment_success_text_dashboard", url=safe_dashboard_url))

    body_parts = [_info_rows_html(rows)]
    if safe_dashboard_url:
        body_parts.append(_cta_button_html(label=cta_label, url=safe_dashboard_url, accent=accent))
    body_parts.append(
        f'<p style="margin:6px 0 0 0;font-size:12px;line-height:1.55;color:{_TEXT_DIM};">{html.escape(footer_note)}</p>'
    )

    rendered = _layout(
        settings=settings,
        preheader=preheader,
        heading=heading,
        intro_html=html.escape(intro),
        body_html="".join(body_parts),
        footer_html=footer,
    )
    return EmailContent(subject=subject, text="\n".join(text_lines), html=rendered)


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
    accent = _safe_color(settings.WEBAPP_PRIMARY_COLOR)
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
        f'<p style="margin:6px 0 0 0;font-size:12px;line-height:1.55;color:{_TEXT_DIM};">{html.escape(note)}</p>'
    )

    rendered = _layout(
        settings=settings,
        preheader=preheader,
        heading=heading,
        intro_html=html.escape(intro),
        body_html="".join(body_parts),
        footer_html=footer,
    )
    return EmailContent(subject=subject, text="\n".join(text_lines), html=rendered)
