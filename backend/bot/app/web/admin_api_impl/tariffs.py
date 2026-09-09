import json
import logging
from pathlib import Path

from aiohttp import web
from pydantic import ValidationError

from bot.app.web.context import (
    get_session_factory,
    get_settings,
)
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    RouteContract,
    ok_envelope_for,
    register_contract,
)
from bot.app.web.webapp.cache_helpers import (
    invalidate_all_webapp_user_payloads,
    refresh_webapp_runtime_after_settings_change,
)
from config.settings import Settings
from config.tariff_period_migration import normalize_tariff_catalog
from config.tariffs_config import TariffsConfig, default_payment_currency_code_for_settings
from db.dal import message_log_dal
from db.tariff_reconciliation import (
    TariffReconciliationReport,
    reconcile_subscription_tariffs,
)
from db.tariff_squad_sync import snapshot_previous_tariff_squads

from .auth import (
    _require_admin_user_id,
)
from .common import (
    _error,
    _ok,
    _tariffs_config_path,
    _write_tariffs_config_file,
)
from .schemas import (
    AdminTariffsCatalogOut,
    AdminTariffsOut,
    ProviderCurrencySupportOut,
    TariffsSaveBody,
)
from .tariff_reconciliation_schemas import (
    AdminTariffReconciliationApplyBody,
    AdminTariffReconciliationOut,
)
from .users_listing import _invalidate_admin_users_list_cache

logger = logging.getLogger(__name__)

_TARIFFS_RESPONSE_SCHEMA = ok_envelope_for(AdminTariffsOut)
_TARIFF_RECONCILIATION_RESPONSE_SCHEMA = ok_envelope_for(AdminTariffReconciliationOut)

register_contract(
    "admin_tariffs_get_route",
    RouteContract(response_schema=_TARIFFS_RESPONSE_SCHEMA, models=(AdminTariffsOut,)),
)
register_contract(
    "admin_tariff_reconciliation_get_route",
    RouteContract(
        response_schema=_TARIFF_RECONCILIATION_RESPONSE_SCHEMA,
        models=(AdminTariffReconciliationOut,),
    ),
)
register_contract(
    "admin_tariff_reconciliation_apply_route",
    RouteContract(
        request_model=AdminTariffReconciliationApplyBody,
        response_schema=_TARIFF_RECONCILIATION_RESPONSE_SCHEMA,
        models=(
            AdminTariffReconciliationApplyBody,
            AdminTariffReconciliationOut,
        ),
    ),
)
register_contract(
    "admin_tariffs_save_route",
    RouteContract(
        request_model=TariffsSaveBody,
        response_schema=_TARIFFS_RESPONSE_SCHEMA,
        models=(TariffsSaveBody, AdminTariffsOut),
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

    return _ok(_tariffs_response_payload(settings, request.app, path=path, config=config))


async def admin_tariffs_save_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    settings: Settings = get_settings(request)
    body = await parse_body_or_400(request, TariffsSaveBody)
    catalog = body.catalog_payload()
    if not isinstance(catalog, dict):
        return _error(400, "invalid_payload", "catalog must be an object")

    path = _tariffs_config_path(settings)
    try:
        previous_config = settings.tariffs_config
    except Exception:
        previous_config = None
    if path.exists() and catalog.get("schema_version", 1) != 2:
        try:
            current_catalog = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            current_catalog = {}
        if isinstance(current_catalog, dict) and current_catalog.get("schema_version") == 2:
            return _error(
                409, "tariff_catalog_version_changed", "Reload the tariff editor before saving"
            )

    try:
        config = TariffsConfig.model_validate(normalize_tariff_catalog(catalog))
    except (ValidationError, ValueError) as exc:
        return _error(400, "invalid_tariffs_config", str(exc))

    if previous_config is not None:
        try:
            await _snapshot_previous_tariff_squads(request, previous_config, config)
        except Exception as exc:
            logger.exception("Failed to snapshot tariff squads before catalog save")
            return _error(500, "tariff_squad_snapshot_failed", str(exc))

    path = _tariffs_config_path(settings)
    try:
        _write_tariffs_config_file(path, config)
    except OSError as exc:
        logger.exception("Failed to write tariffs config to %s", path)
        return _error(500, "write_failed", str(exc))

    try:
        await _run_tariff_reconciliation(
            request,
            config,
            apply=True,
            actor_id=actor_id,
        )
    except Exception as exc:
        logger.exception("Tariff catalog saved but reconciliation failed")
        return _error(
            500,
            "tariffs_saved_reconciliation_failed",
            f"Tariffs were saved, but subscription reconciliation failed: {exc}",
        )

    await refresh_webapp_runtime_after_settings_change(request, updates={}, deletes=[])

    return _ok(_tariffs_response_payload(settings, request.app, path=path, config=config))


async def admin_tariff_reconciliation_get_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = get_settings(request)
    config = settings.tariffs_config
    if config is None:
        return _error(404, "tariffs_not_configured")
    report = await _run_tariff_reconciliation(request, config, apply=False)
    return _ok(AdminTariffReconciliationOut.from_report(report).model_dump(mode="json"))


async def admin_tariff_reconciliation_apply_route(
    request: web.Request,
) -> web.Response:
    actor_id = _require_admin_user_id(request)
    settings: Settings = get_settings(request)
    config = settings.tariffs_config
    if config is None:
        return _error(404, "tariffs_not_configured")
    body = await parse_body_or_400(request, AdminTariffReconciliationApplyBody)
    report = await _run_tariff_reconciliation(
        request,
        config,
        apply=bool(body.apply),
        actor_id=actor_id if body.apply else None,
    )
    return _ok(AdminTariffReconciliationOut.from_report(report).model_dump(mode="json"))


async def _run_tariff_reconciliation(
    request: web.Request,
    config: TariffsConfig,
    *,
    apply: bool,
    actor_id: int | None = None,
) -> TariffReconciliationReport:
    settings: Settings = get_settings(request)
    async_session_factory = get_session_factory(request)
    async with async_session_factory() as session:
        report = await reconcile_subscription_tariffs(session, config, apply=apply)
        if apply:
            if actor_id is not None:
                await message_log_dal.create_message_log_no_commit(
                    session,
                    {
                        "user_id": actor_id,
                        "event_type": "admin_tariff_reconciliation_webapp",
                        "content": (
                            f"scanned={report.scanned} candidates={report.candidates} "
                            f"applied={report.applied} unresolved={report.unresolved}"
                        ),
                        "is_admin_event": True,
                    },
                )
            await session.commit()
    if apply:
        await _invalidate_admin_users_list_cache(settings)
        await invalidate_all_webapp_user_payloads(settings, include_devices=True)
    return report


async def _snapshot_previous_tariff_squads(
    request: web.Request,
    previous_config: TariffsConfig,
    next_config: TariffsConfig,
) -> None:
    async_session_factory = get_session_factory(request)
    async with async_session_factory() as session:
        await snapshot_previous_tariff_squads(session, previous_config, next_config)
        await session.commit()


def _tariffs_response_payload(
    settings: Settings,
    app: web.Application,
    *,
    path: Path,
    config: TariffsConfig | None,
) -> dict[str, object]:
    catalog = (
        AdminTariffsCatalogOut.from_config(config)
        if config is not None
        else AdminTariffsCatalogOut.empty()
    )
    return AdminTariffsOut(
        exists=True if config is not None else path.exists(),
        path=str(path),
        catalog=catalog,
        provider_currency_support=_provider_currency_support_payload(settings, app),
        user_hwid_device_limit=settings.USER_HWID_DEVICE_LIMIT,
    ).to_legacy_payload()


def _provider_currency_support_payload(
    settings: Settings,
    app: web.Application,
) -> list[ProviderCurrencySupportOut]:
    from bot.payment_providers import iter_provider_specs, resolve_provider_presentation

    default_currency = default_payment_currency_code_for_settings(settings)
    providers: list[ProviderCurrencySupportOut] = []
    for spec in iter_provider_specs():
        presentation = resolve_provider_presentation(spec, settings)
        providers.append(
            ProviderCurrencySupportOut.from_provider_spec(
                spec,
                presentation,
                settings=settings,
                app=app,
                default_currency=default_currency,
            )
        )
    return providers
