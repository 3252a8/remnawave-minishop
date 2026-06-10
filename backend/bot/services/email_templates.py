"""Branded HTML email templates that mirror the subscription Mini App look.

The web app uses a dark theme with a configurable accent colour
admin-configured accent colour and logo. The same
accent + logo are reused here so emails feel like part of the product. All
copy goes through the shared `JsonI18n` instance so translations live in
``locales/<lang>.json`` next to the rest of the bot strings.
"""

from __future__ import annotations

import html
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Sequence, Tuple
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from bot.middlewares.i18n import JsonI18n
    from config.settings import Settings

_BG = "#05070a"
_CARD_BG = "#0e1116"
_BORDER = "#1a1f27"
_TEXT = "#e6e9ef"
_TEXT_MUTED = "#9aa3b2"
_TEXT_DIM = "#5d6573"
_DEFAULT_ACCENT = "#00fe7a"
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_EMAIL_LOGO_CONTENT_ID = "webapp-logo"
_WEBAPP_UPLOADED_LOGO_PATH = "/webapp-uploaded-logo"
_WEBAPP_UPLOADED_LOGO_DIR = Path(__file__).resolve().parents[3] / "data" / "webapp-logo" / "uploads"
_WEBAPP_LOGO_MAX_BYTES = 2 * 1024 * 1024
_UPLOADED_LOGO_RE = re.compile(r"logo-[0-9a-f]{16}\.(?:gif|ico|jpe?g|png|svg|webp)")
_LOGO_CONTENT_TYPES = {
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}
_EMAIL_LOGO_PNG_FALLBACK_EXTENSIONS = {".ico", ".webp"}


@dataclass(frozen=True)
class EmailInlineImage:
    content_id: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class EmailContent:
    subject: str
    text: str
    html: str
    inline_images: Tuple[EmailInlineImage, ...] = ()


@dataclass(frozen=True)
class _EmailLayout:
    html: str
    inline_images: Tuple[EmailInlineImage, ...] = ()


def _safe_color(value: Optional[str]) -> str:
    if not value:
        return _DEFAULT_ACCENT
    candidate = value.strip()
    if _HEX_RE.match(candidate):
        return candidate
    return _DEFAULT_ACCENT


def _theme_accent(settings: Settings) -> str:
    primary = _safe_color(getattr(settings, "WEBAPP_PRIMARY_COLOR", None))
    try:
        catalog = getattr(settings, "webapp_themes_catalog", None)
        if catalog is None:
            return primary
        from config.webapp_themes_config import effective_webapp_theme_accent

        return _safe_color(effective_webapp_theme_accent(catalog, primary))
    except Exception:
        return primary


def _public_logo_url(settings: Settings) -> Optional[str]:
    """Email recipients can't reach the in-app /webapp-logo proxy, so only a
    stored public https URL can be used directly. Anything else is dropped."""
    raw = (settings.WEBAPP_LOGO_URL or "").strip()
    if not raw:
        return None
    parsed = urlsplit(raw)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    return raw


def _uploaded_logo_filename(url: str) -> Optional[str]:
    parsed = urlsplit(str(url or ""))
    path = parsed.path if parsed.scheme or parsed.netloc else str(url or "")
    prefix = f"{_WEBAPP_UPLOADED_LOGO_PATH}/"
    if not path.startswith(prefix):
        return None
    filename = path.removeprefix(prefix)
    return filename if _UPLOADED_LOGO_RE.fullmatch(filename) else None


def _inline_uploaded_logo(settings: Settings) -> Optional[EmailInlineImage]:
    filename = _uploaded_logo_filename((settings.WEBAPP_LOGO_URL or "").strip())
    if not filename:
        return None

    content_type = _LOGO_CONTENT_TYPES.get(Path(filename).suffix.lower())
    if not content_type:
        return None

    try:
        uploads_dir = _WEBAPP_UPLOADED_LOGO_DIR.resolve()
        logo_path = (uploads_dir / filename).resolve()
        logo_path.relative_to(uploads_dir)
        body = logo_path.read_bytes()
    except (OSError, ValueError):
        return None

    if not body or len(body) > _WEBAPP_LOGO_MAX_BYTES:
        return None

    content_type, body = _email_logo_payload(filename, content_type, body)

    return EmailInlineImage(
        content_id=_EMAIL_LOGO_CONTENT_ID,
        content_type=content_type,
        data=body,
    )


def _email_logo_payload(filename: str, content_type: str, body: bytes) -> Tuple[str, bytes]:
    suffix = Path(filename).suffix.lower()
    if suffix not in _EMAIL_LOGO_PNG_FALLBACK_EXTENSIONS:
        return content_type, body

    png_body = _static_raster_logo_to_png(body)
    if png_body and len(png_body) <= _WEBAPP_LOGO_MAX_BYTES:
        return "image/png", png_body
    return content_type, body


def _static_raster_logo_to_png(body: bytes) -> Optional[bytes]:
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError:
        return None

    try:
        with Image.open(io.BytesIO(body)) as image:
            image.seek(0)
            if getattr(image, "is_animated", False):
                return None
            source = ImageOps.exif_transpose(image).convert("RGBA")
    except (OSError, UnidentifiedImageError, ValueError, EOFError):
        return None

    if source.width < 1 or source.height < 1 or source.width > 8192 or source.height > 8192:
        return None

    output = io.BytesIO()
    source.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _email_logo(settings: Settings) -> Tuple[Optional[str], Tuple[EmailInlineImage, ...]]:
    inline_logo = _inline_uploaded_logo(settings)
    if inline_logo:
        return f"cid:{inline_logo.content_id}", (inline_logo,)

    public_url = _public_logo_url(settings)
    if public_url:
        return public_url, ()

    return None, ()


def _brand_title(settings: Settings) -> str:
    title = (settings.WEBAPP_TITLE or "").strip()
    return title or "Subscription"


def _normalize_lang(language_code: Optional[str], settings: Settings) -> str:
    value = str(language_code or settings.DEFAULT_LANGUAGE or "ru").strip().lower()
    return value.replace("_", "-") or "ru"


def _resolve_i18n(i18n: Optional[JsonI18n]) -> JsonI18n:
    if i18n is not None:
        return i18n
    from bot.middlewares.i18n import get_i18n_instance

    return get_i18n_instance()


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
    language_code: str,
    preheader: str,
    heading: str,
    intro_html: str,
    body_html: str,
    footer_html: str,
    accent: Optional[str] = None,
) -> _EmailLayout:
    accent = _safe_color(accent) if accent else _theme_accent(settings)
    brand_title = html.escape(_brand_title(settings))
    logo_url, inline_images = _email_logo(settings)
    html_lang = html.escape((language_code or "en").replace("_", "-"), quote=True)
    logo_block = ""
    if logo_url:
        logo_block = (
            f'<img src="{html.escape(logo_url, quote=True)}" width="64" height="64" '
            f'alt="" style="display:block;border:0;outline:none;text-decoration:none;'
            f'border-radius:16px;background:transparent;background-color:transparent;">'
        )

    layout_html = f"""<!DOCTYPE html>
<html lang="{html_lang}" xmlns="http://www.w3.org/1999/xhtml">
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
"""  # noqa: E501
    return _EmailLayout(html=layout_html, inline_images=inline_images)


def _email_content(*, subject: str, text: str, layout: _EmailLayout) -> EmailContent:
    return EmailContent(
        subject=subject,
        text=text,
        html=layout.html,
        inline_images=layout.inline_images,
    )


def _info_rows_html(rows: Sequence[Tuple[str, str]]) -> str:
    if not rows:
        return ""
    last = len(rows) - 1
    cells = []
    for index, (label, value) in enumerate(rows):
        border = "" if index == last else f"border-bottom:1px solid {_BORDER};"
        cells.append(
            f"<tr>"
            f'<td style="padding:11px 0;{border}font-size:12px;color:{_TEXT_DIM};text-transform:uppercase;letter-spacing:0.04em;">{html.escape(label)}</td>'  # noqa: E501
            f"<td align=\"right\" style=\"padding:11px 0;{border}font-family:'JetBrains Mono','SFMono-Regular',Menlo,Consolas,monospace;font-size:14px;font-weight:600;color:{_TEXT};\">{html.escape(value)}</td>"  # noqa: E501
            f"</tr>"
        )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:0 0 16px 0;background:{_BG};border:1px solid {_BORDER};border-radius:14px;padding:6px 16px;">'  # noqa: E501
        + "".join(cells)
        + "</table>"
    )


def _cta_button_html(*, label: str, url: str, accent: str) -> str:
    safe_label = html.escape(label)
    safe_url = html.escape(url, quote=True)
    # Accent green is light, so contrast text is dark; works for the default and similar light accents.  # noqa: E501
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="width:100%;margin:22px 0 18px 0;">'
        f'<tr><td align="center" bgcolor="{accent}" style="background:{accent};border-radius:12px;">'  # noqa: E501
        f'<a href="{safe_url}" target="_blank" rel="noopener" '
        f'style="display:block;width:100%;box-sizing:border-box;padding:15px 22px;'
        f"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"  # noqa: E501
        f'font-size:15px;font-weight:700;color:#05070a;text-decoration:none;letter-spacing:0.02em;text-align:center;">{safe_label}</a>'
        f"</td></tr></table>"
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


_ALLOWED_INLINE_TAGS = {
    "b": "strong",
    "strong": "strong",
    "i": "em",
    "em": "em",
    "u": "u",
    "s": "s",
    "code": "code",
}
_INLINE_TAG_RE = re.compile(r"</?(?:b|strong|i|em|u|s|code)>", re.IGNORECASE)
_ANY_TAG_RE = re.compile(r"<[^>]+>")


def _telegram_html_to_email_html(value: str) -> str:
    """Escape arbitrary text while preserving the tiny Telegram HTML subset we use."""
    source = str(value or "")
    chunks: list[str] = []
    cursor = 0
    for match in _INLINE_TAG_RE.finditer(source):
        chunks.append(html.escape(source[cursor : match.start()]))
        raw_tag = match.group(0)
        closing = raw_tag.startswith("</")
        tag_name = raw_tag.strip("</>").lower()
        mapped = _ALLOWED_INLINE_TAGS.get(tag_name)
        if mapped:
            chunks.append(f"</{mapped}>" if closing else f"<{mapped}>")
        cursor = match.end()
    chunks.append(html.escape(source[cursor:]))
    return "".join(chunks).replace("\n", "<br>")


def _telegram_html_to_text(value: str) -> str:
    return html.unescape(_ANY_TAG_RE.sub("", str(value or "")))


def _format_minutes(seconds: int) -> int:
    return max(1, int(seconds) // 60)


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
    accent = _theme_accent(settings)
    brand = _brand_title(settings)
    sale_base = (sale_mode or "").split("@", 1)[0].split("|", 1)[0]
    is_traffic = sale_base in {
        "traffic",
        "traffic_package",
        "topup",
        "premium_topup",
    }
    is_hwid = sale_base in {"hwid_device", "hwid_devices", "hwid_devices_renewal"}
    is_tariff_upgrade = sale_base == "tariff_upgrade"
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
        intro_key = (
            "email_payment_success_intro_premium_topup"
            if sale_base == "premium_topup"
            else "email_payment_success_intro_traffic"
        )
        intro = _t_text(i18n, lang, intro_key, traffic_gb=traffic_label)
        period_label = _t_text(i18n, lang, "email_payment_success_row_traffic")
        period_value = _t_text(
            i18n, lang, "email_payment_success_traffic_value", traffic_gb=traffic_label
        )
        text = _t_text(
            i18n,
            lang,
            "email_payment_success_text_traffic",
            amount=amount_text,
            traffic_gb=traffic_label,
            end_date=end_date,
        )
    elif is_hwid:
        devices_count = max(0, int(months or 0))
        intro = _t_text(i18n, lang, "email_payment_success_intro_hwid", count=devices_count)
        period_label = _t_text(i18n, lang, "email_payment_success_row_hwid")
        period_value = _t_text(i18n, lang, "email_payment_success_hwid_value", count=devices_count)
        text = _t_text(
            i18n,
            lang,
            "email_payment_success_text_hwid",
            amount=amount_text,
            count=devices_count,
            end_date=end_date,
        )
    elif is_tariff_upgrade:
        intro = _t_text(i18n, lang, "email_payment_success_intro_tariff_upgrade")
        period_label = _t_text(i18n, lang, "email_payment_success_row_operation")
        period_value = _t_text(i18n, lang, "email_payment_success_tariff_upgrade_value")
        text = _t_text(
            i18n,
            lang,
            "email_payment_success_text_tariff_upgrade",
            amount=amount_text,
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
        text_lines.append(
            _t_text(i18n, lang, "email_payment_success_text_dashboard", url=safe_dashboard_url)
        )

    body_parts = [_info_rows_html(rows)]
    if safe_dashboard_url:
        body_parts.append(_cta_button_html(label=cta_label, url=safe_dashboard_url, accent=accent))
    body_parts.append(
        f'<p style="margin:6px 0 0 0;font-size:12px;line-height:1.55;color:{_TEXT_DIM};">{html.escape(footer_note)}</p>'  # noqa: E501
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


def _subscription_lifecycle_title(
    i18n: JsonI18n,
    lang: str,
    notification_key: str,
    *,
    days_left: Optional[int],
    hours_before: Optional[int],
) -> str:
    if notification_key == "before_2d_autorenew":
        return _t_text(i18n, lang, "email_subscription_lifecycle_subject_autorenew")
    if notification_key == "expired":
        return _t_text(i18n, lang, "email_subscription_lifecycle_subject_expired")
    if notification_key == "expired_24h_after":
        return _t_text(i18n, lang, "email_subscription_lifecycle_subject_expired_after")
    if hours_before is not None:
        return _t_text(
            i18n,
            lang,
            "email_subscription_lifecycle_subject_before_hours",
            hours=hours_before,
        )
    return _t_text(
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


def _support_email(
    settings: Settings,
    i18n: Optional[JsonI18n],
    language: Optional[str],
    *,
    subject: str,
    heading: str,
    intro: str,
    rows: Sequence[Tuple[str, str]],
    body_preview: str,
    ticket_url: Optional[str],
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
    i18n: Optional[JsonI18n],
    language: Optional[str],
    *,
    ticket_id: int,
    user_display: str,
    subject: str,
    body_preview: str,
    snapshot_rows: Sequence[Tuple[str, str]],
    ticket_url: Optional[str],
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
    i18n: Optional[JsonI18n],
    language: Optional[str],
    *,
    ticket_id: int,
    user_display: str,
    subject: str,
    body_preview: str,
    snapshot_rows: Sequence[Tuple[str, str]],
    ticket_url: Optional[str],
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
    i18n: Optional[JsonI18n],
    language: Optional[str],
    *,
    ticket_id: int,
    subject: str,
    body_preview: str,
    ticket_url: Optional[str],
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
    i18n: Optional[JsonI18n],
    language: Optional[str],
    *,
    ticket_id: int,
    subject: str,
    body_preview: str = "",
    ticket_url: Optional[str],
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
