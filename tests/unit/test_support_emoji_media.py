import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from sqlalchemy.dialects import sqlite

from bot.app.web.webapp import common
from bot.app.web.webapp import support as support_routes
from bot.services.telegram_emoji_catalog import TelegramEmojiError

EMOJI_ID = "5368651601797984900"
BODY = f'<tg-emoji emoji-id="{EMOJI_ID}">📁</tg-emoji>'


@pytest.fixture
def ticket_media(monkeypatch):
    # Execute the production ownership query rather than mocking its result.
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE support_tickets (ticket_id INTEGER, user_id INTEGER)")
        connection.execute(
            "CREATE TABLE support_ticket_messages (message_id INTEGER, ticket_id INTEGER, "
            "body TEXT, body_format TEXT, is_internal_note BOOLEAN)"
        )
        connection.executemany(
            "INSERT INTO support_tickets VALUES (?, ?)",
            [(7, 42), (8, 99), (9, 42), (10, 42), (11, 42), (12, 42)],
        )
        connection.executemany(
            "INSERT INTO support_ticket_messages VALUES (?, ?, ?, ?, ?)",
            [
                (1, 7, BODY, "html", False),
                (2, 8, BODY, "html", False),
                (3, 9, BODY, "text", False),
                (4, 10, BODY, "html", True),
                (5, 11, '<tg-emoji emoji-id="123">📁</tg-emoji>', "html", False),
                (6, 12, BODY.replace("<", "&lt;").replace(">", "&gt;"), "html", False),
            ],
        )

        class Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def execute(self, statement):
                query = str(
                    statement.compile(
                        dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}
                    )
                )
                row = connection.execute(query).fetchone()
                return SimpleNamespace(scalar_one_or_none=lambda: row[0] if row else None)

        monkeypatch.setattr(support_routes, "get_session_factory", lambda _request: Session)
        monkeypatch.setattr(support_routes, "_require_user_id", lambda _request: 42)
        bot = SimpleNamespace(id=123456)
        monkeypatch.setattr(support_routes, "get_optional_bot", lambda _request: bot)
        media = AsyncMock(return_value=(b"cached-webp", "image/webp"))
        monkeypatch.setattr(support_routes, "media", media)
        yield bot, media


def _request(ticket_id=7, emoji_id=EMOJI_ID):
    return make_mocked_request(
        "GET",
        f"/api/support/tickets/{ticket_id}/emoji/{emoji_id}",
        match_info={"id": str(ticket_id), "emoji_id": emoji_id},
    )


def test_ticket_owner_gets_cached_custom_emoji_without_bot_urls(ticket_media):
    response = asyncio.run(support_routes.support_ticket_emoji_route(_request()))
    assert response.body == b"cached-webp"
    assert response.content_type == "image/webp"
    assert response.headers["Cache-Control"].startswith("private")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    ticket_media[1].assert_awaited_once_with(ticket_media[0], EMOJI_ID)


@pytest.mark.parametrize("ticket_id", [8, 9, 10, 11, 12, 999, 0, 9223372036854775808])
def test_other_owners_internal_notes_plain_text_and_absent_entities_do_not_authorize_media(
    ticket_id, ticket_media
):
    with pytest.raises(web.HTTPNotFound):
        asyncio.run(support_routes.support_ticket_emoji_route(_request(ticket_id=ticket_id)))
    ticket_media[1].assert_not_awaited()


@pytest.mark.parametrize("identifier", ["0", "-1", "a", "1" * 21, "123/extra"])
def test_invalid_media_identifiers_are_rejected(identifier, ticket_media):
    with pytest.raises(web.HTTPNotFound):
        asyncio.run(support_routes.support_ticket_emoji_route(_request(emoji_id=identifier)))
    ticket_media[1].assert_not_awaited()


def test_unauthenticated_ticket_emoji_requires_login(ticket_media, monkeypatch):
    monkeypatch.setattr(common, "_extract_authenticated_user_id", lambda _request: None)
    monkeypatch.setattr(support_routes, "_require_user_id", common._require_user_id)
    with pytest.raises(web.HTTPUnauthorized):
        asyncio.run(support_routes.support_ticket_emoji_route(_request()))
    ticket_media[1].assert_not_awaited()


@pytest.mark.parametrize("ticket_id", [0, 2_147_483_648, 9_223_372_036_854_775_807])
def test_ticket_id_outside_database_integer_range_is_rejected_before_query(
    ticket_id, ticket_media, monkeypatch
):
    factory = MagicMock()
    monkeypatch.setattr(support_routes, "get_session_factory", factory)
    with pytest.raises(web.HTTPNotFound):
        asyncio.run(support_routes.support_ticket_emoji_route(_request(ticket_id=ticket_id)))
    factory.assert_not_called()
    ticket_media[1].assert_not_awaited()


def test_unavailable_media_returns_safe_error(ticket_media):
    ticket_media[1].side_effect = TelegramEmojiError("telegram_emoji_preview_unavailable", 404)
    response = asyncio.run(support_routes.support_ticket_emoji_route(_request()))
    assert response.status == 404
    assert "telegram_emoji_preview_unavailable" in response.text
    assert "api.telegram.org" not in response.text


def test_missing_bot_keeps_ticket_usable(ticket_media, monkeypatch):
    monkeypatch.setattr(support_routes, "get_optional_bot", lambda _request: None)
    response = asyncio.run(support_routes.support_ticket_emoji_route(_request()))
    assert response.status == 503
    ticket_media[1].assert_not_awaited()
