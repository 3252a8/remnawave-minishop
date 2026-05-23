# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405
from .webapp_runtime import refresh_webapp_runtime_after_settings_change


async def admin_tariffs_get_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = request.app["settings"]
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
                    "topup_packages_default": {"rub": [], "stars": []},
                    "tariffs": [],
                },
            }
        )

    return _ok(
        {
            "exists": True,
            "path": str(path),
            "catalog": _tariffs_config_payload(config),
        }
    )


async def admin_tariffs_save_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = request.app["settings"]
    payload = await _read_json(request)
    catalog = payload.get("catalog") if "catalog" in payload else payload
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

    return _ok({"exists": True, "path": str(path), "catalog": _tariffs_config_payload(config)})
