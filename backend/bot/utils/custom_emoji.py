"""Validation and lossless Unicode fallback for Telegram custom emoji HTML."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from config.telegram_emoji import CUSTOM_EMOJI_ID_RE

# Extended_Pictographic (Unicode 17.0), matching the editor's Unicode property.
# Ranges derived from the project's Node Unicode engine; no runtime dependency.
_EXTENDED_PICTOGRAPHIC = re.compile(
    "["
    "\u00a9\u00ae\u203c\u2049\u2122\u2139\u2194-\u2199\u21a9-\u21aa\u231a-\u231b\u2328"
    "\u23cf\u23e9-\u23f3\u23f8-\u23fa\u24c2\u25aa-\u25ab\u25b6\u25c0\u25fb-\u25fe"
    "\u2600-\u2604\u260e\u2611\u2614-\u2615\u2618\u261d\u2620\u2622-\u2623\u2626\u262a"
    "\u262e-\u262f\u2638-\u263a\u2640\u2642\u2648-\u2653\u265f-\u2660\u2663\u2665-\u2666"
    "\u2668\u267b\u267e-\u267f\u2692-\u2697\u2699\u269b-\u269c\u26a0-\u26a1\u26a7"
    "\u26aa-\u26ab\u26b0-\u26b1\u26bd-\u26be\u26c4-\u26c5\u26c8\u26ce-\u26cf\u26d1"
    "\u26d3-\u26d4\u26e9-\u26ea\u26f0-\u26f5\u26f7-\u26fa\u26fd\u2702\u2705\u2708-\u270d"
    "\u270f\u2712\u2714\u2716\u271d\u2721\u2728\u2733-\u2734\u2744\u2747\u274c\u274e"
    "\u2753-\u2755\u2757\u2763-\u2764\u2795-\u2797\u27a1\u27b0\u27bf\u2934-\u2935"
    "\u2b05-\u2b07\u2b1b-\u2b1c\u2b50\u2b55\u3030\u303d\u3297\u3299\U0001f004"
    "\U0001f02c-\U0001f02f\U0001f094-\U0001f09f\U0001f0af-\U0001f0b0\U0001f0c0"
    "\U0001f0cf-\U0001f0d0\U0001f0f6-\U0001f0ff\U0001f170-\U0001f171\U0001f17e-\U0001f17f"
    "\U0001f18e\U0001f191-\U0001f19a\U0001f1ae-\U0001f1e5\U0001f201-\U0001f20f\U0001f21a"
    "\U0001f22f\U0001f232-\U0001f23a\U0001f23c-\U0001f23f\U0001f249-\U0001f25f"
    "\U0001f266-\U0001f321\U0001f324-\U0001f393\U0001f396-\U0001f397\U0001f399-\U0001f39b"
    "\U0001f39e-\U0001f3f0\U0001f3f3-\U0001f3f5\U0001f3f7-\U0001f3fa\U0001f400-\U0001f4fd"
    "\U0001f4ff-\U0001f53d\U0001f549-\U0001f54e\U0001f550-\U0001f567\U0001f56f-\U0001f570"
    "\U0001f573-\U0001f57a\U0001f587\U0001f58a-\U0001f58d\U0001f590\U0001f595-\U0001f596"
    "\U0001f5a4-\U0001f5a5\U0001f5a8\U0001f5b1-\U0001f5b2\U0001f5bc\U0001f5c2-\U0001f5c4"
    "\U0001f5d1-\U0001f5d3\U0001f5dc-\U0001f5de\U0001f5e1\U0001f5e3\U0001f5e8\U0001f5ef"
    "\U0001f5f3\U0001f5fa-\U0001f64f\U0001f680-\U0001f6c5\U0001f6cb-\U0001f6d2"
    "\U0001f6d5-\U0001f6e5\U0001f6e9\U0001f6eb-\U0001f6f0\U0001f6f3-\U0001f6ff"
    "\U0001f7da-\U0001f7ff\U0001f80c-\U0001f80f\U0001f848-\U0001f84f\U0001f85a-\U0001f85f"
    "\U0001f888-\U0001f88f\U0001f8ae-\U0001f8af\U0001f8bc-\U0001f8bf\U0001f8c2-\U0001f8cf"
    "\U0001f8d9-\U0001f8ff\U0001f90c-\U0001f93a\U0001f93c-\U0001f945\U0001f947-\U0001f9ff"
    "\U0001fa58-\U0001fa5f\U0001fa6e-\U0001faff\U0001fc00-\U0001fffd"
    "]"
)


def _emoji_base(code: int) -> bool:
    return _EXTENDED_PICTOGRAPHIC.fullmatch(chr(code)) is not None


def valid_emoji_fallback(value: str) -> bool:
    """Accept one emoji sequence, including modifiers, flags, keycaps and ZWJ."""
    if not value or len(value) > 64 or value != value.strip():
        return False
    if any(0x1F1E6 <= ord(character) <= 0x1F1FF for character in value):
        return len(value) == 2 and all(0x1F1E6 <= ord(character) <= 0x1F1FF for character in value)
    if any(0xE0020 <= ord(character) <= 0xE007F for character in value):
        return (
            value.startswith("\U0001f3f4")
            and value.endswith("\U000e007f")
            and len(value) > 2
            and all(
                0xE0030 <= ord(character) <= 0xE0039 or 0xE0061 <= ord(character) <= 0xE007A
                for character in value[1:-1]
            )
        )
    if "\u20e3" in value:
        return (
            len(value) in {2, 3}
            and value[0] in "0123456789#*"
            and value[-1] == "\u20e3"
            and (len(value) == 2 or value[1] == "\ufe0f")
        )
    for segment in value.split("\u200d"):
        if not segment:
            return False
        codes = [ord(character) for character in segment]
        if 0x20E3 in codes:
            if len(codes) not in {2, 3} or segment[0] not in "0123456789#*":
                return False
            if codes[-1] != 0x20E3 or (len(codes) == 3 and codes[1] != 0xFE0F):
                return False
            continue
        if codes and 0x1F3FB <= codes[-1] <= 0x1F3FF:
            codes.pop()
        if codes and codes[-1] in {0xFE0E, 0xFE0F}:
            codes.pop()
        if len(codes) != 1 or not _emoji_base(codes[0]) or 0x1F3FB <= codes[0] <= 0x1F3FF:
            return False
    return True


def split_decorative_emoji(text: str) -> tuple[str, str]:
    prefix, separator, label = text.partition(" ")
    if separator and valid_emoji_fallback(prefix):
        return prefix, label.lstrip()
    return "", text


class _CustomEmojiValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.active = False
        self.content: list[str] = []
        self.code_depth = 0
        self.error: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.active:
            self.error = "custom_emoji_nested_markup"
        if tag in {"code", "pre"}:
            self.code_depth += 1
        if tag != "tg-emoji":
            return
        identifier = dict(attrs).get("emoji-id") or ""
        if (
            len(attrs) != 1
            or attrs[0][0] != "emoji-id"
            or not CUSTOM_EMOJI_ID_RE.fullmatch(identifier)
        ):
            self.error = "custom_emoji_invalid_id"
        if self.code_depth:
            self.error = "custom_emoji_in_code"
        self.active = True
        self.content = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"code", "pre"}:
            self.code_depth = max(0, self.code_depth - 1)
        if tag == "tg-emoji":
            if not self.active or not valid_emoji_fallback("".join(self.content)):
                self.error = "custom_emoji_invalid_fallback"
            self.active = False
        elif self.active:
            self.error = "custom_emoji_nested_markup"

    def handle_data(self, data: str) -> None:
        if self.active:
            self.content.append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)


def custom_emoji_html_error(value: str) -> str | None:
    if "tg-emoji" not in value.lower():
        return None
    parser = _CustomEmojiValidator()
    parser.feed(value)
    parser.close()
    if parser.active:
        return "custom_emoji_unclosed"
    return parser.error


class _UnicodeFallback(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "tg-emoji":
            self.parts.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag: str) -> None:
        if tag != "tg-emoji":
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.parts.append(f"&#{name};")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "tg-emoji":
            self.parts.append(self.get_starttag_text() or "")


def custom_emoji_unicode_html(value: str) -> str:
    if "tg-emoji" not in value.lower():
        return value
    parser = _UnicodeFallback()
    parser.feed(value)
    parser.close()
    return "".join(parser.parts)
