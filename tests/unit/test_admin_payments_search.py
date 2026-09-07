from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from bot.app.web.admin_api_impl import payments
from db.base import Base
from db.models import Payment, User


@pytest.mark.parametrize(
    ("search", "expected_total"),
    [
        ("@alice", 3),
        ("alice@example.test", 3),
        ("Alice Example", 3),
        ("42", 3),
        ("123456", 3),
        ("-7", 1),
        ("--7", 0),
        ("---42", 0),
        ("#99", 1),
        ("", 5),
        ("%", 0),
        ("_", 0),
        ("\u00b2", 0),
        ("99999999999999999999999999", 0),
        ("missing", 0),
    ],
)
def test_payments_search_filters_total_before_pagination(
    monkeypatch, search: str, expected_total: int
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[User.__table__, Payment.__table__])
    with Session(engine) as session:
        session.add_all(
            [
                User(
                    user_id=42,
                    telegram_id=123456,
                    username="Alice",
                    first_name="Alice",
                    last_name="Example",
                    email="alice@example.test",
                ),
                User(user_id=-7, email="web@example.test"),
            ]
        )
        session.add_all(
            [
                Payment(payment_id=i, user_id=owner, amount=100, currency="RUB", status="succeeded")
                for i, owner in [(1, 42), (2, 42), (3, 42), (4, -7), (5, 99)]
            ]
        )
        session.commit()
        async_session = AsyncMock(spec=AsyncSession)
        async_session.execute.side_effect = session.execute
        context = AsyncMock()
        context.__aenter__.return_value = async_session
        monkeypatch.setattr(
            payments, "get_session_factory", lambda _: MagicMock(return_value=context)
        )
        monkeypatch.setattr(payments, "_require_admin_user_id", lambda _: 1)
        request = cast(
            web.Request, SimpleNamespace(query={"search": search, "page_size": "2", "page": "0"})
        )
        response = asyncio.run(payments.admin_payments_list_route(request))
        payload = json.loads(response.text or "{}")
        assert payload["ok"] is True
        assert payload["total"] == expected_total
        assert len(payload["payments"]) == min(2, expected_total)
    engine.dispose()
