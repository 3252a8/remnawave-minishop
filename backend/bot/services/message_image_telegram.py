"""Prepare stored message images for Telegram's photo upload constraints."""

from __future__ import annotations

import asyncio
import io

from aiogram.types import BufferedInputFile
from PIL import Image, ImageOps

from bot.services.message_image_service import (
    MESSAGE_IMAGE_MAX_DIMENSION,
    MESSAGE_IMAGE_OUTPUT_MAX_BYTES,
    MessageImageError,
    PreparedMessageImage,
    StoredMessageImage,
)

_PHOTO_MAX_ASPECT_RATIO = 20
_photo_semaphore = asyncio.Semaphore(2)


def _encode_photo(body: bytes) -> bytes:
    with Image.open(io.BytesIO(body)) as source:
        rgba = ImageOps.exif_transpose(source).convert("RGBA")
        rgba.thumbnail(
            (MESSAGE_IMAGE_MAX_DIMENSION, MESSAGE_IMAGE_MAX_DIMENSION), Image.Resampling.LANCZOS
        )
        # Flatten transparency and pad narrow banners without cropping their content.
        # sendPhoto permits at most a 20:1 ratio and a width + height of 10000.
        width = max(
            rgba.width, (rgba.height + _PHOTO_MAX_ASPECT_RATIO - 1) // _PHOTO_MAX_ASPECT_RATIO
        )
        height = max(
            rgba.height, (rgba.width + _PHOTO_MAX_ASPECT_RATIO - 1) // _PHOTO_MAX_ASPECT_RATIO
        )
        photo = Image.new("RGB", (width, height), "white")
        photo.paste(rgba, ((width - rgba.width) // 2, (height - rgba.height) // 2), rgba)

    for quality in (90, 80, 70):
        output = io.BytesIO()
        photo.save(output, format="JPEG", quality=quality, optimize=True)
        encoded = output.getvalue()
        if len(encoded) <= MESSAGE_IMAGE_OUTPUT_MAX_BYTES:
            return encoded
    raise MessageImageError("image_too_large", "Telegram photo is too large")


async def prepare_telegram_photo(
    image: PreparedMessageImage | StoredMessageImage,
) -> BufferedInputFile:
    """Use a metadata-free JPEG for Telegram while keeping the stored WebP intact."""
    async with _photo_semaphore:
        body = await image.read_bytes() if isinstance(image, StoredMessageImage) else image.data
        encoded = await asyncio.to_thread(_encode_photo, body)
    return BufferedInputFile(encoded, filename=f"message-{image.digest[:16]}.jpg")
