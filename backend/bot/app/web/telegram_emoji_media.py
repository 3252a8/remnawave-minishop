"""Conditional private image responses, after the caller has checked access."""

from __future__ import annotations

import hashlib

from aiohttp import web

from bot.services import telegram_emoji_storage as storage


def emoji_media_response(
    request: web.Request, content: bytes, mime: str, bot_id: int, emoji_id: str
) -> web.Response:
    etag = f'"{hashlib.sha256(content).hexdigest()}"'
    item = storage.read_item(bot_id, emoji_id)
    versioned = bool(item and request.query.get("v") == storage.media_version(item))
    headers = {
        "Cache-Control": "private, max-age=86400" if versioned else "private, no-cache",
        "ETag": etag,
        # Both bearer and cookie sessions must occupy separate HTTP cache entries.
        "Vary": "Authorization, Cookie",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
    }
    candidates = request.headers.get("If-None-Match", "").split(",")
    if any(value.strip().removeprefix("W/") in {etag, "*"} for value in candidates):
        return web.Response(status=304, headers=headers)
    return web.Response(body=content, content_type=mime, headers=headers)
