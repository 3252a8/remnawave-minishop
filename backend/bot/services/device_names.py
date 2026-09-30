"""Normalization shared by the Web App and the bot for user-chosen device names."""

import unicodedata

DEVICE_NAME_MAX_LENGTH = 32
# Zero-width (non-)joiners hold emoji sequences and some scripts together; every
# other format character (bidi overrides, invisible separators) is dropped.
_KEPT_FORMAT_CHARACTERS = frozenset({"\u200c", "\u200d"})
_SPACE_CATEGORIES = frozenset({"Cc", "Zl", "Zp"})
_DROPPED_CATEGORIES = frozenset({"Cf", "Cs"})


def normalize_device_name(value: object) -> str:
    """Return a single-line name with collapsed whitespace; ``""`` means "use the default"."""
    text = unicodedata.normalize("NFC", str(value or ""))
    kept: list[str] = []
    for char in text:
        category = unicodedata.category(char)
        if category in _SPACE_CATEGORIES:
            kept.append(" ")
        elif category not in _DROPPED_CATEGORIES or char in _KEPT_FORMAT_CHARACTERS:
            kept.append(char)
    return " ".join("".join(kept).split())
