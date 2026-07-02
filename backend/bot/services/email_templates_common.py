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
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

    from config.settings import Settings

_BG = "#05070a"
_CARD_BG = "#0e1116"
_BORDER = "#1a1f27"
_TEXT = "#e6e9ef"
_TEXT_MUTED = "#9aa3b2"
_TEXT_DIM = "#5d6573"
_DEFAULT_ACCENT = "#00fe7a"
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_EMAIL_LOGO_CONTENT_ID = "webapp-logo@remnawave-minishop"
_EMAIL_LOGO_DISPLAY_SIZE = 64
_EMAIL_LOGO_RASTER_SIZE = 128
_EMAIL_LOGO_RASTER_PADDING = 14
_EMAIL_LOGO_BACKGROUND = _CARD_BG
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
_EMAIL_LOGO_SAFE_RASTER_EXTENSIONS = {".gif", ".ico", ".jpg", ".jpeg", ".png", ".webp"}


class _GettextProvider(Protocol):
    def gettext(self, lang_code: str | None, key: str, **kwargs: object) -> str: ...


def _uploaded_logo_dir() -> Path:
    facade = sys.modules.get("bot.services.email_templates")
    if facade is not None:
        value = getattr(facade, "_WEBAPP_UPLOADED_LOGO_DIR", None)
        if value is not None:
            return Path(value)
    return _WEBAPP_UPLOADED_LOGO_DIR


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
    inline_images: tuple[EmailInlineImage, ...] = ()


@dataclass(frozen=True)
class _EmailLayout:
    html: str
    inline_images: tuple[EmailInlineImage, ...] = ()


def _safe_color(value: str | None) -> str:
    if not value:
        return _DEFAULT_ACCENT
    candidate = value.strip()
    if _HEX_RE.match(candidate):
        return candidate
    return _DEFAULT_ACCENT


def _theme_accent(settings: Settings) -> str:
    primary = _safe_color(settings.WEBAPP_PRIMARY_COLOR)
    try:
        catalog = settings.webapp_themes_catalog
        if catalog is None:
            return primary
        from config.webapp_themes_config import effective_webapp_theme_accent

        return _safe_color(effective_webapp_theme_accent(catalog, primary))
    except Exception:
        return primary


def _public_logo_url(settings: Settings) -> str | None:
    """Email recipients can't reach the in-app /webapp-logo proxy, so only a
    stored public https URL can be used directly. Anything else is dropped."""
    raw = (settings.WEBAPP_LOGO_URL or "").strip()
    if not raw:
        return None
    parsed = urlsplit(raw)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    return raw


def _uploaded_logo_filename(url: str) -> str | None:
    parsed = urlsplit(str(url or ""))
    path = parsed.path if parsed.scheme or parsed.netloc else str(url or "")
    prefix = f"{_WEBAPP_UPLOADED_LOGO_PATH}/"
    if not path.startswith(prefix):
        return None
    filename = path.removeprefix(prefix)
    return filename if _UPLOADED_LOGO_RE.fullmatch(filename) else None


def _inline_uploaded_logo(settings: Settings) -> EmailInlineImage | None:
    filename = _uploaded_logo_filename((settings.WEBAPP_LOGO_URL or "").strip())
    if not filename:
        return None

    content_type = _LOGO_CONTENT_TYPES.get(Path(filename).suffix.lower())
    if not content_type:
        return None

    try:
        uploads_dir = _uploaded_logo_dir().resolve()
        logo_path = (uploads_dir / filename).resolve()
        logo_path.relative_to(uploads_dir)
        body = logo_path.read_bytes()
    except (OSError, ValueError):
        return None

    if not body or len(body) > _WEBAPP_LOGO_MAX_BYTES:
        return None

    payload = _email_logo_payload(filename, content_type, body)
    if not payload:
        return None
    content_type, body = payload

    return EmailInlineImage(
        content_id=_EMAIL_LOGO_CONTENT_ID,
        content_type=content_type,
        data=body,
    )


def _email_logo_payload(
    filename: str,
    content_type: str,
    body: bytes,
) -> tuple[str, bytes] | None:
    suffix = Path(filename).suffix.lower()
    if suffix == ".svg":
        return None

    if suffix in _EMAIL_LOGO_SAFE_RASTER_EXTENSIONS:
        png_body = _email_safe_raster_logo_to_png(body)
        if png_body and len(png_body) <= _WEBAPP_LOGO_MAX_BYTES:
            return "image/png", png_body
    return content_type, body


def _email_safe_raster_logo_to_png(body: bytes) -> bytes | None:
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError:
        return None

    try:
        with Image.open(io.BytesIO(body)) as image:
            image.seek(0)
            source = ImageOps.exif_transpose(image).convert("RGBA")
    except (OSError, UnidentifiedImageError, ValueError, EOFError):
        return None

    if source.width < 1 or source.height < 1 or source.width > 8192 or source.height > 8192:
        return None

    source = _crop_transparent_logo_padding(source)
    content_size = _EMAIL_LOGO_RASTER_SIZE - (_EMAIL_LOGO_RASTER_PADDING * 2)
    scale = min(content_size / source.width, content_size / source.height)
    target_size = (
        max(1, int(round(source.width * scale))),
        max(1, int(round(source.height * scale))),
    )
    source = source.resize(target_size, Image.Resampling.LANCZOS)

    canvas = Image.new(
        "RGBA",
        (_EMAIL_LOGO_RASTER_SIZE, _EMAIL_LOGO_RASTER_SIZE),
        _hex_to_rgba(_EMAIL_LOGO_BACKGROUND),
    )
    left = (_EMAIL_LOGO_RASTER_SIZE - source.width) // 2
    top = (_EMAIL_LOGO_RASTER_SIZE - source.height) // 2
    canvas.alpha_composite(source, (left, top))

    output = io.BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()


def _crop_transparent_logo_padding(image: PILImage) -> PILImage:
    bbox = image.getchannel("A").getbbox()
    return image.crop(bbox) if bbox else image


def _hex_to_rgba(value: str) -> tuple[int, int, int, int]:
    normalized = str(value or "#000000").strip().lstrip("#")
    if len(normalized) == 3:
        normalized = "".join(ch * 2 for ch in normalized)
    if len(normalized) != 6:
        normalized = "000000"
    return (
        int(normalized[0:2], 16),
        int(normalized[2:4], 16),
        int(normalized[4:6], 16),
        255,
    )


def _email_logo(settings: Settings) -> tuple[str | None, tuple[EmailInlineImage, ...]]:
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


def _normalize_lang(language_code: str | None, settings: Settings) -> str:
    value = str(language_code or settings.DEFAULT_LANGUAGE or "ru").strip().lower()
    return value.replace("_", "-") or "ru"


def _resolve_i18n(i18n: _GettextProvider | None) -> _GettextProvider:
    if i18n is not None:
        return i18n
    from bot.middlewares.i18n import get_i18n_instance

    return get_i18n_instance()


def _t_html(i18n: _GettextProvider, lang: str, key: str, **kwargs: object) -> str:
    """Translate for HTML context: format args are HTML-escaped, the
    translated template itself is treated as already-safe HTML (locale files
    are author-controlled and may include simple inline tags like <strong>)."""
    safe_kwargs = {k: html.escape(str(v)) for k, v in kwargs.items()}
    return i18n.gettext(lang, key, **safe_kwargs)


def _t_text(i18n: _GettextProvider, lang: str, key: str, **kwargs: object) -> str:
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
    accent: str | None = None,
) -> _EmailLayout:
    accent = _safe_color(accent) if accent else _theme_accent(settings)
    brand_title = html.escape(_brand_title(settings))
    logo_url, inline_images = _email_logo(settings)
    html_lang = html.escape((language_code or "en").replace("_", "-"), quote=True)
    logo_block = ""
    if logo_url:
        logo_size = _EMAIL_LOGO_DISPLAY_SIZE
        logo_block = (
            f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            f'align="center" style="border-collapse:separate;margin:0 auto;">'
            f"<tr>"
            f'<td align="center" valign="middle" width="{logo_size}" height="{logo_size}" '
            f'bgcolor="{_EMAIL_LOGO_BACKGROUND}" style="width:{logo_size}px;'
            f"height:{logo_size}px;background:{_EMAIL_LOGO_BACKGROUND};"
            f"background-color:{_EMAIL_LOGO_BACKGROUND};border-radius:16px;overflow:hidden;"
            f'line-height:0;font-size:0;">'
            f'<img src="{html.escape(logo_url, quote=True)}" width="{logo_size}" '
            f'height="{logo_size}" alt="" style="display:block;width:{logo_size}px;'
            f"height:{logo_size}px;border:0;outline:none;text-decoration:none;"
            f"border-radius:16px;background:{_EMAIL_LOGO_BACKGROUND};"
            f'background-color:{_EMAIL_LOGO_BACKGROUND};line-height:0;">'
            f"</td></tr></table>"
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


def _info_rows_html(rows: Sequence[tuple[str, str]]) -> str:
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
    body = f"{int(rounded)}" if rounded.is_integer() else f"{rounded:.2f}"
    suffix = (currency or "").strip()
    return f"{body} {suffix}".strip()


def _format_traffic(traffic_gb: float | None) -> str:
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
