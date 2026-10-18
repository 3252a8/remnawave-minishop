from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from bot.app.web import session as web_session
from bot.app.web.admin_api_impl import user_relationships
from db.base import Base
from db.dal.user_relationships_dal import has_user_relationships, load_user_relationships
from db.models import User, UserTelegramAvatar
from db.partner_models import PartnerClient, PartnerProfile


def test_complete_graph_preserves_both_edge_kinds_and_excludes_unlinked_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            model.__table__ for model in (User, UserTelegramAvatar, PartnerProfile, PartnerClient)
        ],
    )
    with Session(engine) as session:
        session.add_all(
            [
                User(
                    user_id=user_id,
                    account_id=UUID(int=abs(user_id)),
                    referred_by_id=inviter_id,
                    telegram_id=user_id if user_id > 0 else None,
                    username=f"user{user_id}" if user_id > 0 else None,
                    first_name=f"User {user_id}",
                    email=f"user{user_id}@example.test",
                )
                for user_id, inviter_id in (
                    (1, None),
                    (2, 1),
                    (3, 2),
                    (4, None),
                    (5, 4),
                    (6, None),
                    (7, 7),
                    (8, 999),
                    (9, 10),
                    (10, 9),
                    (-11, None),
                )
            ]
        )
        session.add_all(
            [
                PartnerProfile(
                    partner_id=1,
                    user_id=1,
                    partner_code="first",
                    status="paused",
                    display_label_snapshot="First",
                ),
                PartnerProfile(
                    partner_id=2,
                    user_id=2,
                    partner_code="second",
                    status="closed",
                    display_label_snapshot="Second",
                ),
                PartnerProfile(
                    partner_id=3,
                    user_id=None,
                    partner_code="deleted",
                    display_label_snapshot="Deleted",
                ),
                PartnerProfile(
                    partner_id=4,
                    user_id=7,
                    partner_code="self",
                    display_label_snapshot="Self",
                ),
            ]
        )
        session.flush()
        session.add_all(
            PartnerClient(
                partner_client_id=index,
                partner_id=partner_id,
                client_user_id=client_id,
                public_client_id=f"client-{index}",
                public_label_snapshot="Client",
                source="admin_manual",
            )
            for index, (partner_id, client_id) in enumerate(
                [(1, 4), (2, 3), (1, -11), (1, None), (3, 6), (4, 7)], start=1
            )
        )
        session.add(
            UserTelegramAvatar(
                user_id=1,
                image_bytes=b"avatar",
                content_type="image/jpeg",
                size_bytes=6,
                updated_at=datetime(2026, 10, 18, tzinfo=UTC),
            )
        )
        session.commit()
        async_session = AsyncMock(spec=AsyncSession)
        async_session.execute.side_effect = session.execute
        async_session.scalar.side_effect = session.scalar
        nodes, edges = asyncio.run(load_user_relationships(async_session))
        assert async_session.execute.await_count == 2
        assert {int(user.user_id) for user, _stamp in nodes} == {-11, 1, 2, 3, 4, 5, 9, 10}
        assert set(edges) == {
            (1, 2, "referral"),
            (2, 3, "referral"),
            (4, 5, "referral"),
            (9, 10, "referral"),
            (10, 9, "referral"),
            (1, 4, "partner"),
            (2, 3, "partner"),
            (1, -11, "partner"),
        }
        for user_id in (-11, 1, 2, 3, 4, 5, 9, 10):
            assert asyncio.run(has_user_relationships(async_session, user_id))
        for user_id in (6, 7, 8, 999):
            assert not asyncio.run(has_user_relationships(async_session, user_id))

        async_session.__aenter__.return_value = async_session
        monkeypatch.setattr(
            user_relationships, "get_session_factory", lambda _request: lambda: async_session
        )
        monkeypatch.setattr(user_relationships, "_require_admin_user_id", lambda _request: 1)
        response = asyncio.run(
            user_relationships.admin_user_relationships_route(make_mocked_request("GET", "/"))
        )
        payload = json.loads(response.body)
        assert payload["ok"] is True
        assert len(payload["edges"]) == len(edges)
        root = next(node for node in payload["nodes"] if node["user_id"] == 1)
        assert root["avatar_url"].startswith("/api/admin/users/1/avatar?v=2026-10-18")
        assert root["minishop_id"] == "ms_00000000000000000000000000000001"
        assert root["username"] == "user1"
        assert root["telegram_id"] == 1
        assert root["email"] == "user1@example.test"
        email_only = next(node for node in payload["nodes"] if node["user_id"] == -11)
        assert email_only["telegram_id"] is None
        assert email_only["avatar_url"] is None
    engine.dispose()


def test_empty_graph_has_no_nodes_or_avatar_queries() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = AsyncMock()
    result.all = list
    session.execute.return_value = result
    assert asyncio.run(load_user_relationships(session)) == ([], [])
    assert session.execute.await_count == 1


@pytest.mark.parametrize("user_id", [None, 42])
def test_graph_rejects_anonymous_or_non_admin_before_database_access(
    user_id: int | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = make_mocked_request("GET", "/api/admin/users/relationships")
    monkeypatch.setattr(web_session, "extract_authenticated_user_id", lambda _request: user_id)
    with pytest.raises(web.HTTPUnauthorized if user_id is None else web.HTTPForbidden):
        asyncio.run(user_relationships.admin_user_relationships_route(request))
