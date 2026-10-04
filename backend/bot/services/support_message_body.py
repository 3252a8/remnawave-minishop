"""Ticket message bodies: one stored wire format, three renderings.

A support message is stored either as ``text`` — everything written before the
rich composer existed, and anything a client sends without asking for markup —
or as ``html``: the same Telegram-subset markup the broadcast composer already
produces (``b i u s code a pre blockquote tg-emoji``). The format is stored next to the
body instead of being guessed, so an old plain-text message that happens to
contain ``<b>`` keeps reading as the literal characters its author typed.

Every consumer then asks for the rendering it needs:

- the chat surfaces keep the markup (:func:`sanitize_support_body`'s output is
  what the client re-renders from a whitelist of its own);
- logs and plain-text e-mail previews take :func:`support_body_plain_text`;
- Telegram takes :func:`support_body_telegram_html`, which truncates on tag
  boundaries so a cut-off message never reaches the Bot API half-open.

Truncation is the reason this is a parser and not a regex: slicing a marked-up
body at ``max_length`` splits tags, and Telegram rejects the result.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser

from bot.utils.custom_emoji import valid_emoji_fallback
from config.telegram_menu import CUSTOM_EMOJI_ID_RE

BODY_FORMAT_TEXT = "text"
BODY_FORMAT_HTML = "html"
SUPPORT_BODY_FORMATS = (BODY_FORMAT_TEXT, BODY_FORMAT_HTML)

# The editor ∩ Telegram ∩ e-mail tag set, same as the broadcast composer.
_ALLOWED_TAGS: frozenset[str] = frozenset({"b", "i", "u", "s", "code", "a", "pre", "blockquote"})
# Tags Telegram accepts as synonyms, plus what a paste from a web page brings.
_TAG_ALIASES: dict[str, str] = {
    "strong": "b",
    "em": "i",
    "ins": "u",
    "strike": "s",
    "del": "s",
}
# Tags whose text survives but whose boundaries only mean "new line".
_NEWLINE_TAGS: frozenset[str] = frozenset({"br"})
_PARAGRAPH_TAGS: frozenset[str] = frozenset({"p", "div", "li", "tr", "h1", "h2", "h3", "h4"})
# A link a customer can be told to open. ``javascript:`` and friends are not on
# the list, and neither is a scheme-less href, which resolves against whatever
# origin happens to render the message.
_ALLOWED_HREF_SCHEMES = ("http://", "https://", "tg://", "mailto:")
_MAX_NESTING = 24
_ELLIPSIS = "…"

_EMPTY_TAG_RE = re.compile(r"<(b|i|u|s|code|blockquote|pre)>\s*</\1>")
_EMPTY_LINK_RE = re.compile(r'<a href="[^"]*">\s*</a>')
_EXCESS_BLANK_LINES_RE = re.compile(r"\n{3,}")


class SupportBodyError(ValueError):
    """The body cannot be stored as written (empty after sanitizing)."""


def normalize_body_format(value: str | None) -> str:
    """Coerce a client-supplied format to one this module can render."""

    normalized = str(value or "").strip().lower()
    return normalized if normalized in SUPPORT_BODY_FORMATS else BODY_FORMAT_TEXT


@dataclass(frozen=True)
class SanitizedBody:
    """A body that is safe to store, plus what other channels need from it."""

    html: str
    text: str
    truncated: bool


class _SupportBodyParser(HTMLParser):
    """Rewrite a body into the allowed subset, counting *visible* characters.

    Disallowed tags lose their markup but keep their text — dropping the text
    too would silently swallow whatever a customer pasted from a web page.
    """

    def __init__(self, *, limit: int) -> None:
        super().__init__(convert_charrefs=True)
        self.limit = max(0, int(limit or 0))
        self.truncated = False
        self._html: list[str] = []
        self._text: list[str] = []
        self._open: list[tuple[str, str | None]] = []
        self._length = 0
        self._pre_depth = 0
        self._emoji_id: str | None = None
        self._emoji_content: list[str] = []
        self._emoji_depth = 0
        self._emoji_invalid = False

    # -- output helpers ---------------------------------------------------- #

    def _budget_left(self) -> int:
        return self.limit - self._length if self.limit else -1

    def _emit_text(self, value: str) -> None:
        if not value:
            return
        left = self._budget_left()
        if left == 0:
            self.truncated = True
            return
        if left > 0 and len(value) > left:
            value = value[:left]
            self.truncated = True
        self._length += len(value)
        self._html.append(html.escape(value, quote=False))
        self._text.append(value)

    def _emit_break(self, count: int) -> None:
        """A line break costs nothing against the limit but is not doubled."""

        if not self._html and not self._text:
            return
        if self._budget_left() == 0:
            return
        tail = "".join(self._text[-2:])
        existing = len(tail) - len(tail.rstrip("\n"))
        missing = max(0, count - existing)
        if not missing:
            return
        self._html.append("\n" * missing)
        self._text.append("\n" * missing)

    # -- HTMLParser hooks -------------------------------------------------- #

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._emoji_depth:
            self._emoji_invalid = True
            if tag == "tg-emoji":
                self._emoji_depth += 1
            return
        if tag == "tg-emoji":
            identifier = dict(attrs).get("emoji-id") or ""
            self._emoji_id = identifier if CUSTOM_EMOJI_ID_RE.fullmatch(identifier) else None
            self._emoji_content = []
            self._emoji_depth = 1
            self._emoji_invalid = (
                len(attrs) != 1
                or attrs[0][0] != "emoji-id"
                or any(emitted in {"code", "pre"} for _, emitted in self._open)
            )
            return
        name = _TAG_ALIASES.get(tag, tag)
        if name in _NEWLINE_TAGS:
            self._emit_break(1)
            return
        if self._pre_depth or name not in _ALLOWED_TAGS or len(self._open) >= _MAX_NESTING:
            if name in _PARAGRAPH_TAGS:
                self._emit_break(2)
            self._open.append((tag, None))
            return
        if name == "a":
            href = _clean_href(attrs)
            if not href:
                self._open.append((tag, None))
                return
            self._html.append(f'<a href="{html.escape(href, quote=True)}">')
            self._open.append((tag, "a"))
            return
        if name == "pre":
            self._pre_depth += 1
        self._html.append(f"<{name}>")
        self._open.append((tag, name))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tg-emoji" or self._emoji_depth:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)
            return
        name = _TAG_ALIASES.get(tag, tag)
        if name in _NEWLINE_TAGS:
            self._emit_break(1)
            return
        # A self-closing formatting tag carries no text, so opening and closing
        # it would only produce an empty pair the cleanup pass removes anyway.

    def handle_endtag(self, tag: str) -> None:
        if self._emoji_depth:
            if tag != "tg-emoji":
                self._emoji_invalid = True
                return
            self._emoji_depth -= 1
            if not self._emoji_depth:
                self._flush_emoji()
            return
        name = _TAG_ALIASES.get(tag, tag)
        if name in _NEWLINE_TAGS:
            return
        for index in range(len(self._open) - 1, -1, -1):
            opened, emitted = self._open[index]
            if _TAG_ALIASES.get(opened, opened) != name:
                continue
            # Close everything opened inside the tag first: Telegram parses
            # crossed markup as an error, and the client parser would too.
            for inner_tag, inner_emitted in reversed(self._open[index + 1 :]):
                self._close_emitted(inner_tag, inner_emitted)
            del self._open[index:]
            self._close_emitted(opened, emitted)
            if name in _PARAGRAPH_TAGS:
                self._emit_break(2)
            return
        if name in _PARAGRAPH_TAGS:
            self._emit_break(2)

    def handle_data(self, data: str) -> None:
        if self._emoji_depth:
            self._emoji_content.append(data)
            return
        self._emit_text(data)

    def _flush_emoji(self) -> None:
        fallback = "".join(self._emoji_content)
        if self._emoji_id and not self._emoji_invalid and valid_emoji_fallback(fallback):
            left = self._budget_left()
            if left >= 0 and len(fallback) > left:
                # Never split a flag, modifier or ZWJ sequence inside an entity.
                self.truncated = True
                self._length = self.limit
            else:
                self._html.append(
                    f'<tg-emoji emoji-id="{self._emoji_id}">'
                    f"{html.escape(fallback, quote=False)}</tg-emoji>"
                )
                self._text.append(fallback)
                self._length += len(fallback)
        else:
            self._emit_text(fallback)
        self._emoji_id = None
        self._emoji_content = []

    def _close_emitted(self, tag: str, emitted: str | None) -> None:
        if emitted is None:
            return
        if emitted == "pre":
            self._pre_depth = max(0, self._pre_depth - 1)
        self._html.append(f"</{emitted}>")

    def finish(self) -> SanitizedBody:
        if self._emoji_depth:
            self._emoji_invalid = True
            self._flush_emoji()
        for tag, emitted in reversed(self._open):
            self._close_emitted(tag, emitted)
        self._open.clear()
        rendered = "".join(self._html)
        if self.truncated:
            rendered += _ELLIPSIS
        text = "".join(self._text)
        if self.truncated:
            text += _ELLIPSIS
        return SanitizedBody(
            html=_tidy(rendered),
            text=_EXCESS_BLANK_LINES_RE.sub("\n\n", text).strip(),
            truncated=self.truncated,
        )


def _clean_href(attrs: list[tuple[str, str | None]]) -> str:
    href = next((value for key, value in attrs if key.lower() == "href"), None)
    candidate = str(href or "").strip()
    if not candidate:
        return ""
    return candidate if candidate.lower().startswith(_ALLOWED_HREF_SCHEMES) else ""


def _tidy(value: str) -> str:
    previous = ""
    while previous != value:
        previous = value
        value = _EMPTY_TAG_RE.sub("", value)
        value = _EMPTY_LINK_RE.sub("", value)
    return _EXCESS_BLANK_LINES_RE.sub("\n\n", value).strip()


def _parse(body: str, *, limit: int) -> SanitizedBody:
    parser = _SupportBodyParser(limit=limit)
    try:
        parser.feed(str(body or ""))
        parser.close()
    except Exception:
        # A body the stdlib parser chokes on still has to reach support, so
        # fall back to treating every character as literal text.
        return _plain_body(str(body or ""), limit=limit)
    return parser.finish()


def _plain_body(body: str, *, limit: int) -> SanitizedBody:
    text = str(body or "")
    truncated = bool(limit) and len(text) > limit
    if truncated:
        text = text[:limit] + _ELLIPSIS
    return SanitizedBody(html=html.escape(text, quote=False), text=text, truncated=truncated)


def sanitize_support_body(
    body: str,
    *,
    body_format: str,
    max_length: int,
) -> tuple[str, str]:
    """Return the body to store and the format it is stored in.

    ``max_length`` counts visible characters, so an admin does not lose half a
    sentence to the markup around it. A plain-text body is only trimmed; a
    marked-up one is re-serialized from the parsed structure, which is also
    what drops tags and link schemes the whitelist rejects.
    """

    resolved_format = normalize_body_format(body_format)
    limit = max(0, int(max_length or 0))
    if resolved_format == BODY_FORMAT_TEXT:
        stripped = str(body or "").strip()
        if not stripped:
            raise SupportBodyError("empty_text")
        return (stripped[:limit] if limit else stripped), BODY_FORMAT_TEXT

    parsed = _parse(body, limit=limit)
    if not parsed.text.strip():
        raise SupportBodyError("empty_text")
    return parsed.html, BODY_FORMAT_HTML


def support_body_plain_text(body: str, body_format: str, *, limit: int = 0) -> str:
    """Markup-free body for e-mail previews, log entries and search."""

    if normalize_body_format(body_format) == BODY_FORMAT_TEXT:
        text = str(body or "").strip()
        return f"{text[: limit - 1]}{_ELLIPSIS}" if limit and len(text) > limit else text
    return _parse(body, limit=limit).text


def support_body_telegram_html(body: str, body_format: str, *, limit: int = 0) -> str:
    """Body ready to embed in a Telegram ``parse_mode=HTML`` message.

    Plain text is escaped; markup is re-serialized and cut on a tag boundary,
    so the caller never has to guess whether it may escape the value again.
    """

    if normalize_body_format(body_format) == BODY_FORMAT_TEXT:
        text = str(body or "").strip()
        if limit and len(text) > limit:
            text = f"{text[: limit - 1]}{_ELLIPSIS}"
        return html.escape(text, quote=False)
    return _parse(body, limit=limit).html


__all__ = [
    "BODY_FORMAT_HTML",
    "BODY_FORMAT_TEXT",
    "SUPPORT_BODY_FORMATS",
    "SanitizedBody",
    "SupportBodyError",
    "normalize_body_format",
    "sanitize_support_body",
    "support_body_plain_text",
    "support_body_telegram_html",
]
