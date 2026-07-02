import re
import unicodedata

_OBFUSCATION_CHARS = " .\\-/\\\\•﹒٫＿․·∙‧ꞏ‒–—﹘﹣⁻−"

_URL_PATTERNS = [
    re.compile(r"(?i)https?://\S+"),
    re.compile(r"(?i)www\.\S+"),
    re.compile(r"(?i)tg://\S+"),
    re.compile(r"(?i)telegram\.me\S*"),
    re.compile(r"(?i)t\.me/\+\S*"),
    re.compile(r"(?i)joinchat\S*"),
]

_OBFUSCATED_DOMAIN_PATTERNS = [
    re.compile(
        rf"(?i)[tт][\s{re.escape(_OBFUSCATION_CHARS)}\u2022]*[\.{re.escape(_OBFUSCATION_CHARS)}\u2022]*[\s{re.escape(_OBFUSCATION_CHARS)}\u2022]*[mм][eе]"
    ),
    re.compile(
        rf"(?i)[tт][{re.escape(_OBFUSCATION_CHARS)}\s]*[eе][{re.escape(_OBFUSCATION_CHARS)}\s]*[lłl1i|][{re.escape(_OBFUSCATION_CHARS)}\s]*[eе]"
        rf"[{re.escape(_OBFUSCATION_CHARS)}\s]*[gɢgqг][{re.escape(_OBFUSCATION_CHARS)}\s]*[rр][{re.escape(_OBFUSCATION_CHARS)}\s]*[aа]"
        rf"[{re.escape(_OBFUSCATION_CHARS)}\s]*(?:[mм]|rn)"
    ),
    re.compile(r"(?i)t\.me\S*"),
]

_ENGLISH_SERVICE_PATTERNS = [
    re.compile(r"(?i)telegram"),
    re.compile(r"(?i)teleqram"),
    re.compile(r"(?i)teiegram"),
    re.compile(r"(?i)teieqram"),
    re.compile(r"(?i)telegrarn"),
    re.compile(r"(?i)service"),
    re.compile(r"(?i)notif(?:ication)?"),
    re.compile(r"(?i)system"),
    re.compile(r"(?i)security"),
    re.compile(r"(?i)safety"),
    re.compile(r"(?i)support"),
    re.compile(r"(?i)moderation"),
    re.compile(r"(?i)review"),
    re.compile(r"(?i)compliance"),
    re.compile(r"(?i)abuse"),
    re.compile(r"(?i)spam"),
    re.compile(r"(?i)report"),
]

_RUSSIAN_SERVICE_PATTERNS = [
    re.compile(r"(?i)телеграм\w*"),
    re.compile(r"(?i)служебн\w*"),
    re.compile(r"(?i)уведомлен\w*"),
    re.compile(r"(?i)поддержк\w*"),
    re.compile(r"(?i)безопасн\w*"),
    re.compile(r"(?i)модерац\w*"),
    re.compile(r"(?i)жалоб\w*"),
    re.compile(r"(?i)абуз\w*"),
]

_PRE_LOWER_TRANSLATION = str.maketrans(
    {
        "I": "l",
        "İ": "l",
        "Q": "g",
        "＠": " ",
    }
)

_POST_LOWER_TRANSLATION = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "і": "i",
        "й": "i",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "ch",
        "ш": "sh",
        "щ": "sh",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
        "＿": "_",
    }
)

_NORMALIZED_BANNED_TOKENS = {
    "tme",
    "telegram",
    "teleqram",
    "teiegram",
    "teieqram",
    "telegrarn",
    "joinchat",
    "http",
    "https",
    "www",
    "tg",
    "service",
    "notification",
    "system",
    "security",
    "safety",
    "support",
    "moderation",
    "review",
    "compliance",
    "abuse",
    "spam",
    "report",
}

_USERNAME_PLACEHOLDER = "клиент"


def looks_like_broken_panel_text(value: str | None) -> bool:
    if value is None:
        return False

    text = unicodedata.normalize("NFKC", str(value)).strip()
    if not text:
        return False
    if "\ufffd" in text:
        return True

    meaningful = [ch for ch in text if not ch.isspace()]
    if len(meaningful) < 2:
        return False

    question_count = sum(1 for ch in meaningful if ch == "?")
    if question_count < 2:
        return False

    has_content = any(
        ch != "?" and not unicodedata.category(ch).startswith("P") for ch in meaningful
    )
    return not has_content and question_count / len(meaningful) >= 0.5


def panel_description_from_profile(
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> str:
    lines = []
    for value in (username, first_name, last_name):
        line = (value or "").strip()
        if line and not looks_like_broken_panel_text(line):
            lines.append(line)
    return "\n".join(lines).strip()


def _normalize_for_detection(value: str) -> str:
    if not value:
        return ""

    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.translate(_PRE_LOWER_TRANSLATION)
    normalized = normalized.lower()
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = normalized.translate(_POST_LOWER_TRANSLATION)
    normalized = normalized.replace("rn", "m")

    pattern = rf"[{re.escape(_OBFUSCATION_CHARS)}\s]+"
    normalized = re.sub(pattern, "", normalized)
    normalized = re.sub(r"[^a-z0-9]+", "", normalized)
    return normalized


def _remove_patterns(value: str) -> str:
    updated = value
    for pattern in (
        _URL_PATTERNS
        + _OBFUSCATED_DOMAIN_PATTERNS
        + _ENGLISH_SERVICE_PATTERNS
        + _RUSSIAN_SERVICE_PATTERNS
    ):
        updated = pattern.sub(" ", updated)
    return updated


def _finalize(value: str) -> str | None:
    compacted = re.sub(r"\s+", " ", value)
    compacted = compacted.strip(" \t\r\n-_.,/\\")
    compacted = compacted.strip()
    if not compacted:
        return None

    normalized = _normalize_for_detection(compacted)
    if any(token in normalized for token in _NORMALIZED_BANNED_TOKENS):
        return None
    return compacted


def sanitize_display_name(value: str | None) -> str | None:
    if value is None:
        return None
    clean = value.replace("@", " ")
    clean = _remove_patterns(clean)
    return _finalize(clean)


def sanitize_username(value: str | None) -> str | None:
    if value is None:
        return None
    clean = unicodedata.normalize("NFKC", str(value))
    clean = clean.strip().lstrip("@").strip()
    if not clean:
        return None

    # Telegram usernames are already a constrained identifier, not free-form display text.
    # Do not apply display-name anti-spoofing filters here: they remove words like
    # "service" or "support" from valid usernames such as "name_service".
    if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", clean):
        return clean
    return None


def username_for_display(username: str | None, with_at: bool = False) -> str:
    sanitized = sanitize_username(username)
    if not sanitized:
        return _USERNAME_PLACEHOLDER
    return f"@{sanitized}" if with_at else sanitized


def display_name_or_fallback(
    first_name: str | None,
    fallback: str | None = None,
) -> str:
    sanitized = sanitize_display_name(first_name)
    if sanitized:
        return sanitized
    if fallback is not None:
        return fallback
    return _USERNAME_PLACEHOLDER
