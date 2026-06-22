import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.ttl_cache import AsyncTTLCache
from config.settings import Settings
from config.traffic_strategy import normalize_traffic_limit_strategy
from db.dal import panel_sync_dal
from db.models import PanelSyncStatus

# Static endpoint prefixes used as log/metric labels instead of the raw request
# path. Endpoints embed user identifiers (telegram id, username, email, uuids),
# so logging the path verbatim would leak private data into log files; the
# label keeps only the constant prefix. Longest prefixes first so e.g.

_ENDPOINT_LOG_LABELS = (
    "/users/by-telegram-id",
    "/users/by-username",
    "/users/by-email",
    "/users",
    "/external-squads",
    "/subscriptions/subpage-config",
    "/subscription-page-configs",
    "/hwid/devices/delete",
    "/hwid/devices",
    "/system/stats/bandwidth",
    "/system/stats/nodes",
    "/system/stats",
    "/system/tools/happ/encrypt",
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

from .panel_api_core import PanelApiCoreMixin
from .panel_api_resources import PanelApiResourcesMixin
from .panel_api_squads import PanelApiSquadMutationMixin
from .panel_api_users import PanelApiUsersMixin


class PanelApiService(
    PanelApiUsersMixin,
    PanelApiResourcesMixin,
    PanelApiSquadMutationMixin,
    PanelApiCoreMixin,
):
    pass
