import asyncio
import logging

from .panel_api_core import PanelApiCoreMixin
from .panel_api_resources import PanelApiResourcesMixin
from .panel_api_squads import PanelApiSquadMutationMixin
from .panel_api_users import PanelApiUsersMixin

# Static endpoint prefixes used as log/metric labels instead of the raw request
# path. Endpoints embed user identifiers (telegram id, username, email, uuids),
# so logging the path verbatim would leak private data into log files; the
# label keeps only the constant prefix. Longest prefixes first so e.g.

_ENDPOINT_LOG_LABELS = (
    "/users/by-telegram-id",
    "/users/by-username",
    "/users/by-email",
    "/users/stream",
    "/users",
    "/external-squads",
    "/subscriptions/subpage-config",
    "/subscription-page-configs",
    "/hwid/devices/delete",
    "/hwid/devices/stats",
    "/hwid/devices/top-users",
    "/hwid/devices",
    "/system/stats/bandwidth",
    "/system/stats/nodes",
    "/system/stats",
    "/bandwidth-stats/users",
    "/bandwidth-stats/nodes",
    "/internal-squads",
    "/hosts",
    "/nodes",
)


def _endpoint_log_label(endpoint: str) -> str:
    """Map a request endpoint to a constant, identifier-free label for logs."""
    path = "/" + endpoint.split("?", 1)[0].strip("/")
    for label in _ENDPOINT_LOG_LABELS:
        if path == label or path.startswith(label + "/"):
            return label
    return "/other"


class PanelApiService(
    PanelApiUsersMixin,
    PanelApiResourcesMixin,
    PanelApiSquadMutationMixin,
    PanelApiCoreMixin,
):
    pass


__all__ = [
    "_ENDPOINT_LOG_LABELS",
    "PanelApiService",
    "_endpoint_log_label",
    "asyncio",
    "logging",
]
