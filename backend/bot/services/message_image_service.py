"""Safe, content-addressed storage for images attached to authored messages."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import os
import re
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.email_templates_common import EmailInlineImage
from db.models import MessageImage

MESSAGE_IMAGE_INPUT_MAX_BYTES = 8 * 1024 * 1024
MESSAGE_IMAGE_REQUEST_MAX_BYTES = MESSAGE_IMAGE_INPUT_MAX_BYTES + 512 * 1024
MESSAGE_IMAGE_OUTPUT_MAX_BYTES = 5 * 1024 * 1024
MESSAGE_IMAGE_MAX_DIMENSION = 2560
MESSAGE_IMAGE_MAX_PIXELS = 16_000_000
MESSAGE_IMAGE_CONTENT_TYPE = "image/webp"
MESSAGE_IMAGE_DIR = Path(__file__).resolve().parents[3] / "data" / "message-images"

_IMAGE_ID_RE = re.compile(r"[0-9a-f]{32}")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
_INPUT_FORMATS = {"HEIF", "JPEG", "PNG", "WEBP"}
_PREPARE_IMAGE_CONCURRENCY = 2
_prepare_image_semaphore = asyncio.Semaphore(_PREPARE_IMAGE_CONCURRENCY)

# Disable embedded thumbnails so every accepted HEIC/HEIF upload is decoded
# from its primary image and passes the same pixel, frame and metadata checks.
register_heif_opener(thumbnails=False)


class MessageImageError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class UploadedMessageImage:
    data: bytes
    filename: str = ""
    content_type: str = ""


@dataclass(frozen=True)
class PreparedMessageImage:
    data: bytes
    digest: str
    filename: str
    content_type: str
    width: int
    height: int

    @property
    def size_bytes(self) -> int:
        return len(self.data)


@dataclass(frozen=True)
class StoredMessageImage:
    image_id: str
    digest: str
    filename: str
    content_type: str
    size_bytes: int
    width: int
    height: int
    path: Path

    async def read_bytes(self) -> bytes:
        try:
            body = await asyncio.to_thread(self.path.read_bytes)
        except OSError as exc:
            raise MessageImageError("image_missing", "Stored image is unavailable") from exc
        if len(body) != self.size_bytes or hashlib.sha256(body).hexdigest() != self.digest:
            raise MessageImageError("image_corrupt", "Stored image failed its integrity check")
        return body

    async def email_inline(self, content_id: str = "message-image") -> EmailInlineImage:
        return EmailInlineImage(
            content_id=content_id,
            content_type=self.content_type,
            data=await self.read_bytes(),
        )


def _opaque_rgb(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, "white")
        canvas.paste(rgba, mask=rgba.getchannel("A"))
        return canvas
    return image.convert("RGB")


def _encode_webp(image: Image.Image) -> tuple[bytes, int, int]:
    attempts = ((82, MESSAGE_IMAGE_MAX_DIMENSION), (75, 2240), (68, 1920))
    for quality, max_dimension in attempts:
        candidate = image.copy()
        candidate.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        candidate.save(
            output,
            format="WEBP",
            quality=quality,
            method=6,
            exact=False,
            exif=b"",
            icc_profile=b"",
            xmp=b"",
        )
        body = output.getvalue()
        if len(body) <= MESSAGE_IMAGE_OUTPUT_MAX_BYTES:
            return body, candidate.width, candidate.height
    raise MessageImageError("image_too_large", "Normalized image is too large")


def _prepare_message_image(upload: UploadedMessageImage) -> PreparedMessageImage:
    body = bytes(upload.data or b"")
    if not body:
        raise MessageImageError("empty_image", "Image file is empty")
    if len(body) > MESSAGE_IMAGE_INPUT_MAX_BYTES:
        raise MessageImageError("image_too_large", "Image must be no larger than 8 MiB")

    try:
        # Browser-provided multipart MIME types are advisory. In particular,
        # iOS may export a HEIC selection as a JPEG while declaring image/jpg,
        # or retain a JPEG filename for HEIF bytes. Pillow's decoded format is
        # the security boundary, so validate the bytes below instead.
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(body)) as probe:
                image_format = str(probe.format or "").upper()
                width, height = probe.size
                if image_format not in _INPUT_FORMATS:
                    raise MessageImageError(
                        "unsupported_image",
                        "Only HEIC, HEIF, JPEG, PNG and WebP images are allowed",
                    )
                if int(getattr(probe, "n_frames", 1) or 1) != 1:
                    raise MessageImageError("animated_image", "Animated images are not supported")
                if width < 1 or height < 1 or width * height > MESSAGE_IMAGE_MAX_PIXELS:
                    raise MessageImageError(
                        "image_dimensions", "Image dimensions are not supported"
                    )
                probe.verify()

            with Image.open(io.BytesIO(body)) as source:
                source.load()
                normalized = _opaque_rgb(ImageOps.exif_transpose(source))
                normalized.thumbnail(
                    (MESSAGE_IMAGE_MAX_DIMENSION, MESSAGE_IMAGE_MAX_DIMENSION),
                    Image.Resampling.LANCZOS,
                )
                encoded, final_width, final_height = _encode_webp(normalized)
    except MessageImageError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise MessageImageError("image_dimensions", "Image dimensions are not supported") from exc
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise MessageImageError("invalid_image", "File is not a valid image") from exc

    digest = hashlib.sha256(encoded).hexdigest()
    return PreparedMessageImage(
        data=encoded,
        digest=digest,
        filename=f"message-{digest[:16]}.webp",
        content_type=MESSAGE_IMAGE_CONTENT_TYPE,
        width=final_width,
        height=final_height,
    )


async def prepare_message_image(upload: UploadedMessageImage | None) -> PreparedMessageImage | None:
    if upload is None:
        return None
    async with _prepare_image_semaphore:
        return await asyncio.to_thread(_prepare_message_image, upload)


def _image_path(digest: str) -> Path:
    if not _DIGEST_RE.fullmatch(digest):
        raise MessageImageError("invalid_image", "Stored image identifier is invalid")
    return MESSAGE_IMAGE_DIR / digest[:2] / f"{digest}.webp"


def _write_image_atomically(prepared: PreparedMessageImage) -> Path:
    target = _image_path(prepared.digest)
    if target.is_file():
        try:
            existing = target.read_bytes()
        except OSError:
            existing = b""
        if hashlib.sha256(existing).hexdigest() == prepared.digest:
            return target
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{prepared.digest}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(prepared.data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    finally:
        with contextlib.suppress(OSError):
            Path(temporary_name).unlink(missing_ok=True)
    return target


async def persist_message_image(
    session: AsyncSession,
    prepared: PreparedMessageImage | None,
) -> MessageImage | None:
    if prepared is None:
        return None
    await asyncio.to_thread(_write_image_atomically, prepared)
    image = MessageImage(
        image_id=uuid4().hex,
        digest=prepared.digest,
        filename=prepared.filename,
        content_type=prepared.content_type,
        size_bytes=prepared.size_bytes,
        width=prepared.width,
        height=prepared.height,
    )
    session.add(image)
    await session.flush()
    return image


async def load_message_image(
    session: AsyncSession,
    image_id: str | None,
) -> StoredMessageImage | None:
    normalized_id = str(image_id or "").strip().lower()
    if not _IMAGE_ID_RE.fullmatch(normalized_id):
        return None
    row = await session.get(MessageImage, normalized_id)
    if row is None:
        return None
    digest = str(row.digest or "").strip().lower()
    return StoredMessageImage(
        image_id=str(row.image_id),
        digest=digest,
        filename=str(row.filename),
        content_type=str(row.content_type),
        size_bytes=int(row.size_bytes),
        width=int(row.width),
        height=int(row.height),
        path=_image_path(digest),
    )
