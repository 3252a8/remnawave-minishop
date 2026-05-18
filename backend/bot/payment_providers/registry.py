from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from . import cryptopay, freekassa, platega, severpay, stars, wata, yookassa
from .base import PaymentProviderPresentation, PaymentProviderSpec, ServiceFactoryContext

PAYMENT_PROVIDER_SPECS: tuple[PaymentProviderSpec, ...] = (
    freekassa.SPEC,
    platega.SBP_SPEC,
    platega.CRYPTO_SPEC,
    severpay.SPEC,
    wata.SPEC,
    yookassa.SPEC,
    stars.SPEC,
    cryptopay.SPEC,
)


def iter_provider_specs() -> Iterable[PaymentProviderSpec]:
    return PAYMENT_PROVIDER_SPECS


def get_provider_spec(method: str) -> Optional[PaymentProviderSpec]:
    normalized = str(method or "").strip().lower()
    for spec in PAYMENT_PROVIDER_SPECS:
        if normalized in spec.method_ids:
            return spec
    return None


def _setting_value(settings: Any, key: str) -> Optional[str]:
    if settings is None:
        return None
    value = getattr(settings, key, None)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _presentation_setting(spec: PaymentProviderSpec, suffix: str) -> str:
    return f"PAYMENT_{spec.settings_key}_{suffix}"


def _normalize_language(language: Optional[str], settings: Any = None) -> str:
    value = language or getattr(settings, "DEFAULT_LANGUAGE", None) or "ru"
    normalized = str(value).strip().lower().split("-", 1)[0].split("_", 1)[0]
    return normalized or "ru"


def _localized_setting_value(
    settings: Any,
    spec: PaymentProviderSpec,
    suffix: str,
    language: str,
) -> Optional[str]:
    return _setting_value(
        settings,
        _presentation_setting(spec, f"{suffix}_{language.upper()}"),
    )


def _localized_default(
    values: Optional[Mapping[str, str]],
    language: str,
    fallback: Optional[str],
) -> Optional[str]:
    if not values:
        return fallback
    return (
        values.get(language)
        or values.get("en")
        or values.get("ru")
        or next(iter(values.values()), None)
        or fallback
    )


def resolve_provider_presentation(
    spec: PaymentProviderSpec,
    settings: Any = None,
    *,
    language: Optional[str] = None,
    translate: Optional[Callable[[str], str]] = None,
) -> PaymentProviderPresentation:
    lang = _normalize_language(language, settings)
    webapp_label = (
        _localized_setting_value(settings, spec, "WEBAPP_LABEL", lang)
        or _localized_default(spec.webapp_labels, lang, spec.webapp_label)
        or spec.label
    )
    webapp_icon = (
        _setting_value(settings, _presentation_setting(spec, "WEBAPP_ICON"))
        or spec.webapp_icon
    )
    telegram_label_override = _localized_setting_value(
        settings,
        spec,
        "TELEGRAM_LABEL",
        lang,
    )
    telegram_emoji_override = _setting_value(
        settings, _presentation_setting(spec, "TELEGRAM_EMOJI")
    )
    telegram_label = (
        telegram_label_override
        or _localized_default(spec.telegram_labels, lang, None)
        or spec.label
    )
    telegram_emoji = telegram_emoji_override or spec.default_telegram_emoji

    if (
        not telegram_label_override
        and not spec.telegram_labels
        and translate
        and spec.button_text_key
    ):
        telegram_label = translate(spec.button_text_key)

    return PaymentProviderPresentation(
        webapp_label=webapp_label,
        webapp_icon=webapp_icon,
        telegram_label=telegram_label,
        telegram_emoji=telegram_emoji,
        telegram_customized=bool(telegram_label_override or telegram_emoji_override),
    )


def provider_telegram_button_text(
    spec: PaymentProviderSpec,
    settings: Any,
    translate: Callable[[str], str],
    *,
    language: Optional[str] = None,
) -> str:
    presentation = resolve_provider_presentation(spec, settings, language=language)
    if presentation.telegram_emoji:
        return f"{presentation.telegram_emoji} {presentation.telegram_label}".strip()
    return presentation.telegram_label


def iter_unique_provider_routers():
    seen: set[int] = set()
    for spec in PAYMENT_PROVIDER_SPECS:
        router = spec.load_router()
        if not router:
            continue
        marker = id(router)
        if marker in seen:
            continue
        seen.add(marker)
        yield router


def iter_service_keys() -> Iterable[str]:
    seen: set[str] = set()
    for spec in PAYMENT_PROVIDER_SPECS:
        if not spec.service_key or spec.service_key in seen:
            continue
        seen.add(spec.service_key)
        yield spec.service_key


def iter_service_specs() -> Iterable[PaymentProviderSpec]:
    seen: set[str] = set()
    for spec in PAYMENT_PROVIDER_SPECS:
        if not spec.service_key or not spec.create_service or spec.service_key in seen:
            continue
        seen.add(spec.service_key)
        yield spec


def build_provider_services(ctx: ServiceFactoryContext) -> Dict[str, Any]:
    services: Dict[str, Any] = {}
    for spec in iter_service_specs():
        services[spec.service_key] = spec.create_service(ctx)
    return services


def provider_label_map(settings: Any = None, language: Optional[str] = None) -> Dict[str, str]:
    labels: Dict[str, str] = {}
    for spec in PAYMENT_PROVIDER_SPECS:
        presentation = resolve_provider_presentation(
            spec,
            settings,
            language=language,
        )
        label = presentation.telegram_label if presentation.telegram_customized else spec.label
        labels.setdefault(spec.provider_key, label)
        for method in spec.method_ids:
            labels.setdefault(method, label)
    return labels


def provider_emoji_map(settings: Any = None) -> Dict[str, str]:
    emojis: Dict[str, str] = {}
    for spec in PAYMENT_PROVIDER_SPECS:
        emoji = resolve_provider_presentation(spec, settings).telegram_emoji
        emojis.setdefault(spec.provider_key, emoji)
        for method in spec.method_ids:
            emojis.setdefault(method, emoji)
    return emojis


def pending_statuses() -> List[str]:
    statuses = ["pending"]
    for spec in PAYMENT_PROVIDER_SPECS:
        if spec.pending_status not in statuses:
            statuses.append(spec.pending_status)
    return statuses
