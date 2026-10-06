"""Validation and lossless Unicode fallback for Telegram custom emoji HTML."""

from __future__ import annotations

from bisect import bisect_right
from html.parser import HTMLParser

from config.telegram_emoji import CUSTOM_EMOJI_ID_RE

# Extended_Pictographic (Unicode 17.0), matching the editor's Unicode property.
# Ranges derived from the project's Node Unicode engine; no runtime dependency.
_EXTENDED_PICTOGRAPHIC_RANGES = (
    (0x00A9, 0x00A9),
    (0x00AE, 0x00AE),
    (0x203C, 0x203C),
    (0x2049, 0x2049),
    (0x2122, 0x2122),
    (0x2139, 0x2139),
    (0x2194, 0x2199),
    (0x21A9, 0x21AA),
    (0x231A, 0x231B),
    (0x2328, 0x2328),
    (0x23CF, 0x23CF),
    (0x23E9, 0x23F3),
    (0x23F8, 0x23FA),
    (0x24C2, 0x24C2),
    (0x25AA, 0x25AB),
    (0x25B6, 0x25B6),
    (0x25C0, 0x25C0),
    (0x25FB, 0x25FE),
    (0x2600, 0x2604),
    (0x260E, 0x260E),
    (0x2611, 0x2611),
    (0x2614, 0x2615),
    (0x2618, 0x2618),
    (0x261D, 0x261D),
    (0x2620, 0x2620),
    (0x2622, 0x2623),
    (0x2626, 0x2626),
    (0x262A, 0x262A),
    (0x262E, 0x262F),
    (0x2638, 0x263A),
    (0x2640, 0x2640),
    (0x2642, 0x2642),
    (0x2648, 0x2653),
    (0x265F, 0x2660),
    (0x2663, 0x2663),
    (0x2665, 0x2666),
    (0x2668, 0x2668),
    (0x267B, 0x267B),
    (0x267E, 0x267F),
    (0x2692, 0x2697),
    (0x2699, 0x2699),
    (0x269B, 0x269C),
    (0x26A0, 0x26A1),
    (0x26A7, 0x26A7),
    (0x26AA, 0x26AB),
    (0x26B0, 0x26B1),
    (0x26BD, 0x26BE),
    (0x26C4, 0x26C5),
    (0x26C8, 0x26C8),
    (0x26CE, 0x26CF),
    (0x26D1, 0x26D1),
    (0x26D3, 0x26D4),
    (0x26E9, 0x26EA),
    (0x26F0, 0x26F5),
    (0x26F7, 0x26FA),
    (0x26FD, 0x26FD),
    (0x2702, 0x2702),
    (0x2705, 0x2705),
    (0x2708, 0x270D),
    (0x270F, 0x270F),
    (0x2712, 0x2712),
    (0x2714, 0x2714),
    (0x2716, 0x2716),
    (0x271D, 0x271D),
    (0x2721, 0x2721),
    (0x2728, 0x2728),
    (0x2733, 0x2734),
    (0x2744, 0x2744),
    (0x2747, 0x2747),
    (0x274C, 0x274C),
    (0x274E, 0x274E),
    (0x2753, 0x2755),
    (0x2757, 0x2757),
    (0x2763, 0x2764),
    (0x2795, 0x2797),
    (0x27A1, 0x27A1),
    (0x27B0, 0x27B0),
    (0x27BF, 0x27BF),
    (0x2934, 0x2935),
    (0x2B05, 0x2B07),
    (0x2B1B, 0x2B1C),
    (0x2B50, 0x2B50),
    (0x2B55, 0x2B55),
    (0x3030, 0x3030),
    (0x303D, 0x303D),
    (0x3297, 0x3297),
    (0x3299, 0x3299),
    (0x1F004, 0x1F004),
    (0x1F02C, 0x1F02F),
    (0x1F094, 0x1F09F),
    (0x1F0AF, 0x1F0B0),
    (0x1F0C0, 0x1F0C0),
    (0x1F0CF, 0x1F0D0),
    (0x1F0F6, 0x1F0FF),
    (0x1F170, 0x1F171),
    (0x1F17E, 0x1F17F),
    (0x1F18E, 0x1F18E),
    (0x1F191, 0x1F19A),
    (0x1F1AE, 0x1F1E5),
    (0x1F201, 0x1F20F),
    (0x1F21A, 0x1F21A),
    (0x1F22F, 0x1F22F),
    (0x1F232, 0x1F23A),
    (0x1F23C, 0x1F23F),
    (0x1F249, 0x1F25F),
    (0x1F266, 0x1F321),
    (0x1F324, 0x1F393),
    (0x1F396, 0x1F397),
    (0x1F399, 0x1F39B),
    (0x1F39E, 0x1F3F0),
    (0x1F3F3, 0x1F3F5),
    (0x1F3F7, 0x1F3FA),
    (0x1F400, 0x1F4FD),
    (0x1F4FF, 0x1F53D),
    (0x1F549, 0x1F54E),
    (0x1F550, 0x1F567),
    (0x1F56F, 0x1F570),
    (0x1F573, 0x1F57A),
    (0x1F587, 0x1F587),
    (0x1F58A, 0x1F58D),
    (0x1F590, 0x1F590),
    (0x1F595, 0x1F596),
    (0x1F5A4, 0x1F5A5),
    (0x1F5A8, 0x1F5A8),
    (0x1F5B1, 0x1F5B2),
    (0x1F5BC, 0x1F5BC),
    (0x1F5C2, 0x1F5C4),
    (0x1F5D1, 0x1F5D3),
    (0x1F5DC, 0x1F5DE),
    (0x1F5E1, 0x1F5E1),
    (0x1F5E3, 0x1F5E3),
    (0x1F5E8, 0x1F5E8),
    (0x1F5EF, 0x1F5EF),
    (0x1F5F3, 0x1F5F3),
    (0x1F5FA, 0x1F64F),
    (0x1F680, 0x1F6C5),
    (0x1F6CB, 0x1F6D2),
    (0x1F6D5, 0x1F6E5),
    (0x1F6E9, 0x1F6E9),
    (0x1F6EB, 0x1F6F0),
    (0x1F6F3, 0x1F6FF),
    (0x1F7DA, 0x1F7FF),
    (0x1F80C, 0x1F80F),
    (0x1F848, 0x1F84F),
    (0x1F85A, 0x1F85F),
    (0x1F888, 0x1F88F),
    (0x1F8AE, 0x1F8AF),
    (0x1F8BC, 0x1F8BF),
    (0x1F8C2, 0x1F8CF),
    (0x1F8D9, 0x1F8FF),
    (0x1F90C, 0x1F93A),
    (0x1F93C, 0x1F945),
    (0x1F947, 0x1F9FF),
    (0x1FA58, 0x1FA5F),
    (0x1FA6E, 0x1FAFF),
    (0x1FC00, 0x1FFFD),
)
_EXTENDED_PICTOGRAPHIC_STARTS = tuple(start for start, _ in _EXTENDED_PICTOGRAPHIC_RANGES)


def _emoji_base(code: int) -> bool:
    index = bisect_right(_EXTENDED_PICTOGRAPHIC_STARTS, code) - 1
    return index >= 0 and code <= _EXTENDED_PICTOGRAPHIC_RANGES[index][1]


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
