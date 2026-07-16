from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, cast

from . import (
    cloudpayments,
    cryptopay,
    freekassa,
    heleket,
    lava,
    overpay,
    pally,
    paykilla,
    platega,
    qa,
    severpay,
    stars,
    stripe,
    wata,
    yookassa,
)
from .base import (
    PaymentProviderPresentation,
    PaymentProviderSpec,
    ProviderConfigBundle,
    ProviderManifestField,
    ServiceFactoryContext,
)
from .shared import RecurringProviderService

PAYMENT_PROVIDER_SPECS: tuple[PaymentProviderSpec, ...] = (
    freekassa.SPEC,
    platega.SBP_SPEC,
    platega.CRYPTO_SPEC,
    severpay.SPEC,
    wata.SPEC,
    wata.CRYPTO_SPEC,
    yookassa.SPEC,
    stars.SPEC,
    cryptopay.SPEC,
    heleket.SPEC,
    paykilla.SPEC,
    lava.SPEC,
    pally.SPEC,
    cloudpayments.SPEC,
    overpay.SPEC,
    stripe.SPEC,
    qa.SPEC,
)


# Provider configs (env-loaded BaseSettings models) live here as a process-wide
# singleton populated by build_provider_configs() on startup. Modules that need
# to read provider configs without changing call signatures (e.g. presentation
# resolution from arbitrary callers) can look them up via current_provider_configs().
#
# Keyed by ``service_key`` because multiple SPECs (Platega SBP / Platega Crypto)
# can share the same backing service. Per-SPEC presentation overrides live in
# ``_provider_presentations`` instead, indexed by ``spec.id``.
_provider_configs: dict[str, ProviderConfigBundle] = {}
_provider_presentations: dict[str, Any] = {}


def iter_provider_specs() -> Iterable[PaymentProviderSpec]:
    return PAYMENT_PROVIDER_SPECS


def get_provider_spec(method: str) -> PaymentProviderSpec | None:
    normalized = str(method or "").strip().lower()
    for spec in PAYMENT_PROVIDER_SPECS:
        if normalized in spec.method_ids:
            return spec
    return None


def build_provider_configs(*, force: bool = False) -> dict[str, ProviderConfigBundle]:
    """Instantiate per-provider BaseSettings models declared on each SPEC.

    Returns a mapping ``service_key`` → ``ProviderConfigBundle(config, presentation)``.
    For SPECs that share a service (Platega SBP + Platega Crypto), only the
    first one's presentation lands in the shared bundle — per-SPEC presentation
    overrides live separately in ``_provider_presentations`` keyed by ``spec.id``.

    Idempotent by default: if bundles already exist in the process-wide cache
    we return them as-is. Pass ``force=True`` to rebuild from env (used by
    tests after monkeypatching env vars). The non-force path is critical for
    runtime: ``load_overrides_from_db`` builds bundles first and then writes
    DB-persisted overrides into them — a later non-force rebuild from
    ``build_core_services`` would otherwise wipe those overrides.
    """
    if _provider_configs and not force:
        return dict(_provider_configs)

    from .base import provider_env_file

    env_file = provider_env_file()
    init_kwargs: dict[str, Any] = {"_env_file": env_file}

    bundles: dict[str, ProviderConfigBundle] = {}
    presentations: dict[str, Any] = {}
    seen_services: set[str] = set()
    for spec in PAYMENT_PROVIDER_SPECS:
        if spec.presentation_class is not None:
            presentations[spec.id] = spec.presentation_class(**init_kwargs)

        if not spec.service_key or spec.service_key in seen_services:
            continue
        if spec.config_class is None and spec.presentation_class is None:
            continue
        seen_services.add(spec.service_key)
        bundles[spec.service_key] = ProviderConfigBundle(
            config=spec.config_class(**init_kwargs) if spec.config_class else None,
            presentation=presentations.get(spec.id),
        )
    _provider_configs.clear()
    _provider_configs.update(bundles)
    _provider_presentations.clear()
    _provider_presentations.update(presentations)
    return bundles


def get_spec_presentation(spec_id: str) -> Any | None:
    return _provider_presentations.get(spec_id)


def current_provider_configs() -> Mapping[str, ProviderConfigBundle]:
    return _provider_configs


def get_provider_bundle(service_key: str | None) -> ProviderConfigBundle | None:
    if not service_key:
        return None
    return _provider_configs.get(service_key)


def _setting_value(source: Any, key: str) -> str | None:
    if source is None:
        return None
    value = getattr(source, key, None)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _presentation_setting(spec: PaymentProviderSpec, suffix: str) -> str:
    return f"PAYMENT_{spec.settings_key}_{suffix}"


def _normalize_language(language: str | None, settings: Any = None) -> str:
    value = language or (settings.DEFAULT_LANGUAGE if settings is not None else None) or "ru"
    normalized = str(value).strip().lower().split("-", 1)[0].split("_", 1)[0]
    return normalized or "ru"


def _presentation_attr(suffix: str, language: str | None = None) -> str:
    """Attribute name on a provider's presentation BaseSettings model.

    Mirrors the legacy ``PAYMENT_<ID>_<suffix>`` env name, but without the
    ``PAYMENT_<ID>_`` prefix (which is supplied by env_prefix on the model).
    """
    if language:
        return f"{suffix}_{language.upper()}"
    return suffix


def _provider_presentation_value(
    spec: PaymentProviderSpec,
    suffix: str,
    *,
    language: str | None = None,
) -> str | None:
    presentation = _provider_presentations.get(spec.id)
    if presentation is None:
        bundle = _provider_configs.get(spec.service_key) if spec.service_key else None
        presentation = bundle.presentation if bundle else None
    if presentation is None:
        return None
    attr = _presentation_attr(suffix, language=language)
    return _setting_value(presentation, attr)


def _localized_setting_value(
    settings: Any,
    spec: PaymentProviderSpec,
    suffix: str,
    language: str,
) -> str | None:
    # 1) Per-provider presentation model (new pattern) takes priority.
    provider_value = _provider_presentation_value(spec, suffix, language=language)
    if provider_value is not None:
        return provider_value
    # 2) Legacy: PAYMENT_<ID>_<suffix>_<LANG> on the global Settings.
    return _setting_value(
        settings,
        _presentation_setting(spec, f"{suffix}_{language.upper()}"),
    )


def _bare_setting_value(
    settings: Any,
    spec: PaymentProviderSpec,
    suffix: str,
) -> str | None:
    provider_value = _provider_presentation_value(spec, suffix)
    if provider_value is not None:
        return provider_value
    return _setting_value(settings, _presentation_setting(spec, suffix))


def _localized_default(
    values: Mapping[str, str] | None,
    language: str,
    fallback: str | None,
) -> str | None:
    if not values:
        return fallback
    return (
        values.get(language)
        or values.get("en")
        or values.get("ru")
        or next(iter(values.values()), None)
        or fallback
    )


# Specs whose default button labels have language-specific variants in the
# locale files. Spec labels themselves stay English-only in code; providers
# listed here resolve ``payment_provider_<id>_<kind>_label`` first.
_LOCALE_LABEL_SPEC_IDS = frozenset({"freekassa", "platega_sbp", "platega_crypto"})


def _locale_label(spec_id: str, kind: str, language: str) -> str | None:
    if spec_id not in _LOCALE_LABEL_SPEC_IDS:
        return None
    from bot.middlewares.i18n import get_i18n_instance

    key = f"payment_provider_{spec_id}_{kind}_label"
    text = get_i18n_instance().gettext(language, key)
    if text and text != key:
        return str(text)
    return None


def resolve_provider_presentation(
    spec: PaymentProviderSpec,
    settings: Any = None,
    *,
    language: str | None = None,
) -> PaymentProviderPresentation:
    lang = _normalize_language(language, settings)
    webapp_label = (
        _localized_setting_value(settings, spec, "WEBAPP_LABEL", lang)
        or _locale_label(spec.id, "webapp", lang)
        or _localized_default(spec.webapp_labels, lang, spec.webapp_label)
        or spec.label
    )
    webapp_icon = _bare_setting_value(settings, spec, "WEBAPP_ICON") or spec.webapp_icon
    telegram_label_override = _localized_setting_value(
        settings,
        spec,
        "TELEGRAM_LABEL",
        lang,
    )
    telegram_emoji_override = _bare_setting_value(settings, spec, "TELEGRAM_EMOJI")
    telegram_label = (
        telegram_label_override
        or _locale_label(spec.id, "telegram", lang)
        or _localized_default(spec.telegram_labels, lang, None)
        or spec.label
    )
    telegram_emoji = telegram_emoji_override or spec.default_telegram_emoji

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
    *,
    language: str | None = None,
) -> str:
    presentation = resolve_provider_presentation(spec, settings, language=language)
    if presentation.telegram_emoji:
        return f"{presentation.telegram_emoji} {presentation.telegram_label}".strip()
    return presentation.telegram_label


def iter_unique_provider_routers() -> Iterable[Any]:
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


def build_provider_services(ctx: ServiceFactoryContext) -> dict[str, object]:
    services: dict[str, object] = {}
    for spec in iter_service_specs():
        service_key = spec.service_key
        create_service = spec.create_service
        if not service_key or create_service is None:
            continue
        services[service_key] = create_service(ctx)
    return services


def recurring_provider_services(
    services: Mapping[str, object],
) -> dict[str, RecurringProviderService]:
    """Map ``provider_key`` to service for every recurring-capable provider.

    Keyed by ``provider_key`` because that is what ``Subscription.provider``
    stores, so the renewal worker can resolve the service straight from a
    subscription row without knowing about service-key naming.
    """
    recurring: dict[str, RecurringProviderService] = {}
    for spec in PAYMENT_PROVIDER_SPECS:
        if not spec.supports_recurring or not spec.service_key:
            continue
        service = services.get(spec.service_key)
        if service is not None:
            recurring[spec.provider_key] = cast(RecurringProviderService, service)
    return recurring


def provider_supports_recurring(provider: str | None) -> bool:
    spec = get_provider_spec(provider or "")
    return bool(spec and spec.supports_recurring)


def provider_label_map(settings: Any = None, language: str | None = None) -> dict[str, str]:
    labels: dict[str, str] = {}
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


def provider_emoji_map(settings: Any = None) -> dict[str, str]:
    emojis: dict[str, str] = {}
    for spec in PAYMENT_PROVIDER_SPECS:
        emoji = resolve_provider_presentation(spec, settings).telegram_emoji
        emojis.setdefault(spec.provider_key, emoji)
        for method in spec.method_ids:
            emojis.setdefault(method, emoji)
    return emojis


def pending_statuses() -> list[str]:
    statuses = ["pending"]
    for spec in PAYMENT_PROVIDER_SPECS:
        if spec.pending_status not in statuses:
            statuses.append(spec.pending_status)
    return statuses


def iter_provider_manifest_fields() -> Iterable[tuple[PaymentProviderSpec, ProviderManifestField]]:
    """Yield (spec, manifest_field) for every fragment declared on a provider SPEC."""
    for spec in PAYMENT_PROVIDER_SPECS:
        emitted_keys: set[str] = set()
        for field in spec.manifest_fields:
            emitted_keys.add(field.key)
            yield spec, field
        admin_only_field = provider_admin_only_manifest_field(spec)
        if admin_only_field is not None and admin_only_field.key not in emitted_keys:
            yield spec, admin_only_field


def find_manifest_owner(key: str) -> tuple[PaymentProviderSpec, ProviderManifestField] | None:
    """Find which provider owns a manifest key (if any)."""
    for spec, field in iter_provider_manifest_fields():
        if field.key == key:
            return spec, field
    return None


def provider_admin_only_manifest_field(
    spec: PaymentProviderSpec,
) -> ProviderManifestField | None:
    if spec.config_class is None:
        return None

    subsection = spec.label
    for field in spec.manifest_fields:
        if field.subsection:
            subsection = field.subsection
            break

    return ProviderManifestField(
        spec.admin_only_field_key,
        "bool",
        "Only for admins",
        (
            "Shows this payment method only to users from ADMIN_IDS. "
            "Webhooks and provider services remain active for admin test payments."
        ),
        subsection=subsection,
        attr=spec.admin_only_config_attr,
        i18n_label_key="admin_settings_provider_admin_only_label",
        i18n_description_key="admin_settings_provider_admin_only_description",
    )


def provider_admin_only_pairs() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for spec in PAYMENT_PROVIDER_SPECS:
        pair = (spec.enabled_field_key, spec.admin_only_field_key)
        if pair in seen:
            continue
        seen.add(pair)
        pairs.append(pair)
    return pairs


def _webhook_spec_for(spec: PaymentProviderSpec) -> PaymentProviderSpec | None:
    if spec.webhook_path and spec.webhook_route:
        return spec
    if not spec.service_key:
        return None
    for candidate in PAYMENT_PROVIDER_SPECS:
        if (
            candidate.service_key == spec.service_key
            and candidate.webhook_path
            and candidate.webhook_route
        ):
            return candidate
    return None


def provider_webhook_metadata(spec: PaymentProviderSpec) -> dict[str, Any] | None:
    """Return admin-manifest webhook metadata for a provider SPEC.

    Some visible payment buttons share one backing service and webhook route
    (for example Platega SBP and Platega Crypto), so presentation-only specs
    inherit the route from their service sibling.
    """
    webhook_spec = _webhook_spec_for(spec)
    if webhook_spec is None or not webhook_spec.webhook_path:
        return None
    try:
        path = str(webhook_spec.webhook_path(None) or "").strip()
    except Exception:
        return None
    if not path:
        return None
    return {
        "provider_id": spec.id,
        "provider_label": spec.label,
        "webhook_provider_id": webhook_spec.id,
        "webhook_path": path,
        "webhook_requires_base_url": bool(webhook_spec.webhook_requires_base_url),
    }


def provider_admin_metadata(spec: PaymentProviderSpec) -> dict[str, Any]:
    """Return admin UI metadata shared by all manifest fields of a provider."""

    metadata: dict[str, Any] = {
        "provider_id": spec.id,
        "provider_label": spec.label,
    }
    info_url = str(spec.info_url or spec.currency_support_url or "").strip()
    logo_url = str(spec.logo_url or "").strip()
    if info_url:
        metadata["provider_info_url"] = info_url
    if logo_url:
        metadata["provider_logo_url"] = logo_url
    webhook_metadata = provider_webhook_metadata(spec)
    if webhook_metadata:
        metadata.update(webhook_metadata)
    return metadata


def manifest_field_default(
    spec: PaymentProviderSpec,
    manifest_field: ProviderManifestField,
) -> str | None:
    """Resolve the SPEC-declared default for a presentation manifest field.

    Used by the admin UI to render a placeholder/hint that shows users what
    button text or icon the bot falls back to when they leave the override
    blank. Returns None for non-presentation fields or attributes we don't
    have a mapping for (admin shouldn't render a misleading hint).
    """
    if manifest_field.target != "presentation":
        return None
    attr = manifest_field.attr or manifest_field.key
    if attr == "WEBAPP_LABEL_RU":
        return _localized_default(spec.webapp_labels, "ru", spec.webapp_label) or spec.label
    if attr == "WEBAPP_LABEL_EN":
        return _localized_default(spec.webapp_labels, "en", spec.webapp_label) or spec.label
    if attr == "WEBAPP_ICON":
        return spec.webapp_icon
    if attr == "TELEGRAM_LABEL_RU":
        return _localized_default(spec.telegram_labels, "ru", None) or spec.label
    if attr == "TELEGRAM_LABEL_EN":
        return _localized_default(spec.telegram_labels, "en", None) or spec.label
    if attr == "TELEGRAM_EMOJI":
        return spec.default_telegram_emoji
    return None
