"""Compatibility re-export facade for the admin Mini App API."""

from bot.app.web.admin_api_impl import (
    _runtime as _runtime,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    ads as _ads,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    auth as _auth,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    backups as _backups,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    broadcast as _broadcast,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    common as _common,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    health as _health,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    logs as _logs,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    panel as _panel,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    payments as _payments,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    promos as _promos,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    routes as _routes,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    settings as _settings,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    stats as _stats,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    support as _support,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    sync as _sync,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    tariffs as _tariffs,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    themes as _themes,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    translations as _translations,  # noqa: F401
)
from bot.app.web.admin_api_impl import (
    users as _users,  # noqa: F401
)
from bot.app.web.admin_api_impl.auth import (
    admin_auth_middleware,
)
from bot.app.web.admin_api_impl.common import (
    _premium_traffic_list_payload,
)
from bot.app.web.admin_api_impl.routes import (
    setup_admin_routes,
)
from bot.app.web.admin_api_impl.settings import (
    admin_settings_get_route,
    app_settings_dal,
)
from bot.app.web.admin_api_impl.stats import (
    admin_me_route,
)

__all__ = [
    "_premium_traffic_list_payload",
    "admin_auth_middleware",
    "admin_me_route",
    "admin_settings_get_route",
    "app_settings_dal",
    "setup_admin_routes",
]
