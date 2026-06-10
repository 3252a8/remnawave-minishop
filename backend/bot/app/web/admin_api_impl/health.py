# ruff: noqa: F401,F403,F405,I001
from datetime import datetime, timezone

from ._runtime import *  # noqa: F403,F405
from .auth import _require_admin_user_id
from .common import _ok
from bot.services.config_health_service import collect_config_alerts


async def admin_health_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    refresh = str(request.query.get("refresh", "")).strip().lower() in {"1", "true", "yes"}
    alerts = await collect_config_alerts(request, refresh=refresh)
    return _ok(
        {
            "alerts": alerts,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    )
