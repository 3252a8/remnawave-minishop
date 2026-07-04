import logging
from typing import Any, Dict, List

from aiohttp import web
from pydantic import ValidationError

from bot.app.web.context import (
    get_settings,
)
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    BOOLEAN_SCHEMA,
    STRING_SCHEMA,
    RouteContract,
    loose_array_schema,
    loose_object_schema,
    ok_envelope_with,
    register_contract,
)
from bot.app.web.webapp.cache_helpers import refresh_webapp_runtime_after_settings_change
from config.settings import Settings
from config.tariffs_config import TariffsConfig, default_payment_currency_code_for_settings

from .auth import (
    _require_admin_user_id,
)
from .common import (
    _error,
    _ok,
    _tariffs_config_path,
    _tariffs_config_payload,
    _write_tariffs_config_file,
)
from .schemas import TariffsSaveBody

logger = logging.getLogger(__name__)

_TARIFFS_RESPONSE_SCHEMA = ok_envelope_with(
    {
        "exists": BOOLEAN_SCHEMA,
        "path": STRING_SCHEMA,
        "catalog": loose_object_schema(),
        "provider_currency_support": loose_array_schema(),
    }
)

register_contract(
    "admin_tariffs_get_route",
    RouteContract(response_schema=_TARIFFS_RESPONSE_SCHEMA, models=(TariffsConfig,)),
)
register_contract(
    "admin_tariffs_save_route",
    RouteContract(
        request_model=TariffsSaveBody,
        response_schema=_TARIFFS_RESPONSE_SCHEMA,
        models=(TariffsConfig,),
    ),
)


async def admin_tariffs_get_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = get_settings(request)
    path = _tariffs_config_path(settings)

    try:
        config = settings.tariffs_config
    except Exception as exc:
        logger.warning("Invalid tariffs config requested from admin UI: %s", exc)
        return _error(400, "invalid_tariffs_config", str(exc))

    if config is None:
        return _ok(
            {
                "exists": path.exists(),
                "path": str(path),
                "catalog": {
                    "default_tariff": "",
                    "default_currency": "cny",
                    "topup_packages_default": {"cny": [], "stars": []},
                    "tariffs": [],
                },
                "provider_currency_support": _provider_currency_support_payload(
                    settings,
                    request.app,
                    default_currency_code="CNY",
                ),
            }
        )

    return _ok(
        {
            "exists": True,
            "path": str(path),
            "catalog": _tariffs_config_payload(config),
            "provider_currency_support": _provider_currency_support_payload(
                settings,
                request.app,
                default_currency_code=config.default_payment_currency_code,
            ),
        }
    )


async def admin_tariffs_save_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = get_settings(request)
    body = await parse_body_or_400(request, TariffsSaveBody)
    catalog = body.catalog_payload()
    if not isinstance(catalog, dict):
        return _error(400, "invalid_payload", "catalog must be an object")

    try:
        config = TariffsConfig.model_validate(catalog)
    except (ValidationError, ValueError) as exc:
        return _error(400, "invalid_tariffs_config", str(exc))

    path = _tariffs_config_path(settings)
    try:
        _write_tariffs_config_file(path, config)
    except OSError as exc:
        logger.exception("Failed to write tariffs config to %s", path)
        return _error(500, "write_failed", str(exc))

    await refresh_webapp_runtime_after_settings_change(request, updates={}, deletes=[])

    return _ok(
        {
            "exists": True,
            "path": str(path),
            "catalog": _tariffs_config_payload(config),
            "provider_currency_support": _provider_currency_support_payload(
                settings,
                request.app,
                default_currency_code=config.default_payment_currency_code,
            ),
        }
    )


def _provider_currency_support_payload(
    settings: Settings,
    app: web.Application,
    default_currency_code: str | None = None,
) -> List[Dict[str, Any]]:
    from bot.payment_providers import iter_provider_specs, resolve_provider_presentation

    default_currency = default_currency_code or default_payment_currency_code_for_settings(settings)
    providers: List[Dict[str, Any]] = []
    for spec in iter_provider_specs():
        presentation = resolve_provider_presentation(spec, settings)
        supported = spec.supported_currency_codes(settings)
        providers.append(
            {
                "id": spec.id,
                "provider_key": spec.provider_key,
                "provider_label": _provider_currency_support_label(spec),
                "settings_path": _provider_settings_path(spec),
                "label": presentation.webapp_label or spec.label,
                "telegram_label": presentation.telegram_label,
                "icon": presentation.webapp_icon,
                "enabled": spec.is_effectively_enabled(settings),
                "configured": spec.is_service_configured(app),
                "admin_only": spec.is_admin_only_enabled(settings),
                "price_source": spec.price_source,
                "currencies": list(supported) if supported is not None else None,
                "accepts_any_currency": supported is None,
                "supports_default_currency": spec.is_usable_for_payment_currency(
                    settings,
                    default_currency,
                ),
                "directly_supports_default_currency": spec.supports_currency(
                    settings,
                    default_currency,
                ),
                "default_currency": default_currency,
                "note": spec.currency_support_note,
                "docs_url": spec.currency_support_url,
            }
        )
    return providers


def _provider_currency_support_label(spec: Any) -> str:
    if spec.id == "platega_sbp":
        return "Platega SBP/card"
    if spec.id == "platega_crypto":
        return "Platega Crypto"
    return str(spec.label or spec.id)


def _provider_settings_path(spec: Any) -> List[str]:
    if spec.id == "platega_sbp":
        return ["payments", "platega", "sbp"]
    if spec.id == "platega_crypto":
        return ["payments", "platega", "crypto"]
    return ["payments", str(spec.provider_key or spec.id).replace("_", "-")]
