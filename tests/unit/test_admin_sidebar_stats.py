from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from bot.app.web.admin_api_impl import support


def test_support_stats_include_partner_attention_only_on_request() -> None:
    session = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    stats = {"total_unread_admin": 4}
    attention = {"pending_applications": 3, "requested_withdrawals": 2, "total": 5}
    with (
        patch.object(support, "_require_admin_user_id", return_value=1),
        patch.object(support, "get_session_factory", return_value=factory),
        patch.object(support.support_dal, "admin_stats", AsyncMock(return_value=stats)),
        patch.object(
            support.partner_dal, "attention_counts", AsyncMock(return_value=attention)
        ) as counts,
    ):
        for query, expected in (
            ("", stats),
            ("?include_partner_attention=1", {**stats, "partner_attention_total": 5}),
        ):
            request = make_mocked_request("GET", f"/api/admin/support/stats{query}")
            response = asyncio.run(support.admin_support_stats_route(request))
            assert json.loads(response.text or "{}") == {"ok": True, "stats": expected}
            if not query:
                counts.assert_not_awaited()
        counts.assert_awaited_once_with(session)


def test_combined_stats_require_admin_access_before_reading_any_counts() -> None:
    request = make_mocked_request("GET", "/api/admin/support/stats?include_partner_attention=1")
    with (
        patch.object(support, "_require_admin_user_id", side_effect=web.HTTPForbidden),
        patch.object(support, "get_session_factory") as factory,
        pytest.raises(web.HTTPForbidden),
    ):
        asyncio.run(support.admin_support_stats_route(request))
    factory.assert_not_called()
