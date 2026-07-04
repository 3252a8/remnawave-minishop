import json
import re
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCALES_DIR = REPO_ROOT / "locales"
ADMIN_FRONTEND_DIR = REPO_ROOT / "frontend" / "src" / "admin"
SETTINGS_MANIFEST_PATH = (
    REPO_ROOT / "frontend" / "src" / "lib" / "webapp" / "settingsManifest.generated.json"
)
WEBAPP_CONSTANTS_PATH = REPO_ROOT / "frontend" / "src" / "lib" / "webapp" / "constants.js"
THEMES_DIR = REPO_ROOT / "data" / "themes"
TARIFFS_EXAMPLE_PATH = REPO_ROOT / "data" / "tariffs.example.json"
SUBSCRIPTION_GUIDES_DEFAULT_PATH = (
    REPO_ROOT / "backend" / "config" / "defaults" / "subscription_page_multiapp.json"
)

PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
LATIN_WORD_RE = re.compile(r"[A-Za-z]{3,}")

ZH_CN_REQUIRED_PREFIXES = (
    "wa_",
    "email_",
    "menu_",
    "webapp_",
    "payment_",
)

ZH_CN_ALLOWED_LATIN_WORDS = {
    "API",
    "App",
    "AppStore",
    "ASCII",
    "BEPUSDT",
    "Crypto",
    "CryptoPay",
    "CloudPayments",
    "GB",
    "FreeKassa",
    "Heleket",
    "HTTP",
    "HTTPS",
    "ID",
    "IP",
    "JSON",
    "Key",
    "Lava",
    "LAVA",
    "Mini",
    "PayKilla",
    "Pally",
    "Platega",
    "Public",
    "Remnawave",
    "RUB",
    "Secret",
    "SeverPay",
    "SMTP",
    "Stars",
    "Stripe",
    "Telegram",
    "Token",
    "URL",
    "USDT",
    "VPN",
    "Wata",
    "Web",
    "Webhook",
    "Widget",
    "Windows",
    "YooKassa",
}
ZH_CN_ALLOWED_EXACT_VALUES = {
    "{current}/{max}",
    "/GB",
}

ZH_CN_SETTINGS_FORBIDDEN_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"小节",
        r"配置[^。]*已启用",
        r"配置[A-Za-z]",
        r"已启用$",
        r"WebApp",
        r"TTLminutes|lifetime秒数|includeservices|trustedIPS|publicID|terminalID|TO币种|APIURL|API键",
        r"afterexpire|before|localretention|st频率gy",
        r"1month|[3-9]月数|1[0-9]月数|月数|秒数|分钟数",
        r"基础URL|失败URL|链接TTL|公钥键|令牌",
    )
)

ZH_CN_ADMIN_COPY_FORBIDDEN_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"套餐(标签|提示|列|占位提示|定价.*说明|model|hidden)",
        r"优惠码(标签|列|效果.*说明|效果.*example|范围|类型mixed|条件说明)",
        r"\b(single|example|until|standalone|FOR|hidden|model)\b",
        r"Price,|Price in|Package ₽|Package ⭐",
        r"ЦЕНА|Пакет",
    )
)


def _locale(language: str) -> dict[str, str]:
    return json.loads((LOCALES_DIR / f"{language}.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _admin_web_locale_keys() -> frozenset[str]:
    keys: set[str] = set()
    for path in ADMIN_FRONTEND_DIR.rglob("*"):
        if path.suffix not in {".svelte", ".js", ".ts"}:
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"""\bat\(\s*["'`](?P<key>[^"'`$]+)["'`]""", text):
            keys.add(f"admin_{match.group('key')}")
        for match in re.finditer(r"""\bt\(\s*["'`](?P<key>[^"'`$]+)["'`]""", text):
            key = match.group("key")
            if key.startswith(("admin_", "wa_")):
                keys.add(key)

    manifest = json.loads(SETTINGS_MANIFEST_PATH.read_text(encoding="utf-8"))

    def collect_manifest_i18n(value: object) -> None:
        if isinstance(value, dict):
            for item_key, item_value in value.items():
                if item_key.startswith("i18n_") and isinstance(item_value, str):
                    keys.add(item_value)
                collect_manifest_i18n(item_value)
        elif isinstance(value, list):
            for item in value:
                collect_manifest_i18n(item)

    collect_manifest_i18n(manifest)
    return frozenset(keys)


@lru_cache(maxsize=1)
def _locale_key_aliases() -> dict[str, str]:
    text = WEBAPP_CONSTANTS_PATH.read_text(encoding="utf-8")
    match = re.search(r"export const LOCALE_KEY_ALIASES = \{(?P<body>.*?)\};", text, re.DOTALL)
    assert match is not None
    return dict(
        re.findall(
            r"""(?P<key>[A-Za-z0-9_]+):\s*["'`](?P<value>[^"'`]+)["'`]""", match.group("body")
        )
    )


def _resolve_locale_key(key: str) -> str:
    aliases = _locale_key_aliases()
    value = key
    seen: set[str] = set()
    while value in aliases and value not in seen:
        seen.add(value)
        value = aliases[value]
    return value


def _placeholders(value: str) -> set[str]:
    return set(PLACEHOLDER_RE.findall(value))


def _html_tags(value: str) -> list[str]:
    return [tag.split()[0].replace("<", "").replace(">", "") for tag in HTML_TAG_RE.findall(value)]


def _contains_cjk(value: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in value)


def _is_technical_or_brand_only(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return True
    if stripped in ZH_CN_ALLOWED_EXACT_VALUES:
        return True
    words = set(LATIN_WORD_RE.findall(stripped))
    return bool(words) and words.issubset(ZH_CN_ALLOWED_LATIN_WORDS)


def _is_relevant_zh_cn_key(key: str) -> bool:
    return key.startswith(ZH_CN_REQUIRED_PREFIXES) or key in _admin_web_locale_keys()


def test_zh_cn_has_same_locale_keys_as_english():
    en = _locale("en")
    zh = _locale("zh-cn")

    assert set(zh) == set(en)


def test_zh_cn_preserves_placeholders_and_html_tags():
    en = _locale("en")
    zh = _locale("zh-cn")

    mismatches = {}
    for key, en_value in en.items():
        zh_value = zh[key]
        if _placeholders(en_value) != _placeholders(zh_value):
            mismatches[key] = {
                "en_placeholders": sorted(_placeholders(en_value)),
                "zh_placeholders": sorted(_placeholders(zh_value)),
            }
        if _html_tags(en_value) != _html_tags(zh_value):
            mismatches.setdefault(key, {})["html_tags"] = {
                "en_tags": _html_tags(en_value),
                "zh_tags": _html_tags(zh_value),
            }

    assert mismatches == {}


def test_zh_cn_user_visible_locales_are_not_untranslated_english():
    en = _locale("en")
    zh = _locale("zh-cn")

    untranslated = []
    for key, en_value in en.items():
        if not _is_relevant_zh_cn_key(key):
            continue
        zh_value = zh[key]
        if zh_value == en_value and not _is_technical_or_brand_only(zh_value):
            untranslated.append(f"{key}={zh_value}")
            continue
        if not _contains_cjk(zh_value) and not _is_technical_or_brand_only(zh_value):
            untranslated.append(f"{key}={zh_value}")

    assert untranslated == []


def test_zh_cn_runtime_catalogs_have_chinese_names():
    missing = []
    for theme_path in THEMES_DIR.glob("*/theme.json"):
        theme = json.loads(theme_path.read_text(encoding="utf-8"))
        if "zh-cn" not in theme.get("names", {}):
            missing.append(str(theme_path.relative_to(REPO_ROOT)))

    tariffs = json.loads(TARIFFS_EXAMPLE_PATH.read_text(encoding="utf-8"))
    for tariff in tariffs.get("tariffs", []):
        for field in ("names", "descriptions", "premium_names"):
            if field in tariff and "zh-cn" not in tariff[field]:
                missing.append(f"data/tariffs.example.json:{tariff.get('key')}.{field}")

    guides = json.loads(SUBSCRIPTION_GUIDES_DEFAULT_PATH.read_text(encoding="utf-8"))
    if "zh-cn" not in guides.get("locales", []):
        missing.append("subscription_page_multiapp.json:locales")

    def walk_guides(value: object, path: str = "subscription_page_multiapp.json") -> None:
        if isinstance(value, dict):
            if "en" in value and "ru" in value and "zh-cn" not in value:
                missing.append(path)
            for item_key, item_value in value.items():
                walk_guides(item_value, f"{path}.{item_key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk_guides(item, f"{path}[{index}]")

    walk_guides(guides)

    assert missing == []


def test_admin_frontend_fallbacks_are_backed_by_locale_keys():
    messages = _locale("zh-cn")
    missing = []
    fallback_re = re.compile(
        r"""\bat\(\s*["'`](?P<key>[^"'`$]+)["'`]\s*,\s*\{[^)]*?\}\s*,\s*["'`](?P<fallback>[^"'`$]*)["'`]""",
        re.DOTALL,
    )

    for path in ADMIN_FRONTEND_DIR.rglob("*"):
        if path.suffix not in {".svelte", ".js", ".ts"}:
            continue
        text = path.read_text(encoding="utf-8")
        for match in fallback_re.finditer(text):
            locale_key = _resolve_locale_key(f"admin_{match.group('key')}")
            fallback = match.group("fallback")
            if locale_key not in messages and LATIN_WORD_RE.search(fallback):
                missing.append(f"{path.relative_to(REPO_ROOT)}:{locale_key}={fallback}")

    assert missing == []


def test_zh_cn_settings_copy_is_operator_readable():
    zh = _locale("zh-cn")

    awkward = []
    for key, value in zh.items():
        if not key.startswith("admin_settings_"):
            continue
        if any(pattern.search(value) for pattern in ZH_CN_SETTINGS_FORBIDDEN_PATTERNS):
            awkward.append(f"{key}={value}")

    assert awkward == []


def test_zh_cn_admin_commerce_copy_is_operator_readable():
    zh = _locale("zh-cn")

    awkward = []
    for key, value in zh.items():
        if not key.startswith(("admin_tariff_", "admin_tariffs_", "admin_promo_")):
            continue
        if any(pattern.search(value) for pattern in ZH_CN_ADMIN_COPY_FORBIDDEN_PATTERNS):
            awkward.append(f"{key}={value}")

    assert awkward == []


def test_zh_cn_settings_manifest_labels_have_locale_entries():
    zh = _locale("zh-cn")
    manifest = json.loads(SETTINGS_MANIFEST_PATH.read_text(encoding="utf-8"))

    missing = []
    for section in manifest:
        for field in section.get("fields", []):
            for attr in ("i18n_label_key", "i18n_description_key"):
                key = field.get(attr)
                if key and key not in zh:
                    missing.append(f"{field.get('key')}:{attr}={key}")

    assert missing == []
