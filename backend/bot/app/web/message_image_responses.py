"""Private immutable responses for normalized message images."""

from __future__ import annotations

import asyncio

from aiohttp import web

from bot.services.message_image_service import StoredMessageImage


async def message_image_response(image: StoredMessageImage) -> web.StreamResponse:
    try:
        stat = await asyncio.to_thread(image.path.stat)
    except OSError:
        raise web.HTTPNotFound() from None
    if not image.path.is_file() or stat.st_size != image.size_bytes:
        raise web.HTTPNotFound()
    response = web.FileResponse(image.path)
    response.content_type = image.content_type
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["ETag"] = f'"{image.digest}"'
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Disposition"] = f'inline; filename="{image.filename}"'
    return response
