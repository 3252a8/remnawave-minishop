from __future__ import annotations

import io

import pytest
from PIL import Image

from bot.services import message_image_service
from bot.services.message_image_service import (
    MESSAGE_IMAGE_CONTENT_TYPE,
    MessageImageError,
    UploadedMessageImage,
    _prepare_message_image,
    _write_image_atomically,
)


def _image_bytes(format_name: str, size: tuple[int, int] = (160, 120)) -> bytes:
    output = io.BytesIO()
    exif = Image.Exif()
    exif[0x010E] = "ignored metadata"
    Image.new("RGB", size, (32, 96, 180)).save(output, format=format_name, exif=exif)
    return output.getvalue()


def test_uploaded_image_is_reencoded_as_static_webp_without_metadata() -> None:
    prepared = _prepare_message_image(
        UploadedMessageImage(
            data=_image_bytes("JPEG"),
            filename="invoice.exe",
            content_type="application/octet-stream",
        )
    )

    assert prepared.content_type == MESSAGE_IMAGE_CONTENT_TYPE == "image/webp"
    assert prepared.filename.endswith(".webp")
    assert prepared.data[:4] == b"RIFF"
    with Image.open(io.BytesIO(prepared.data)) as decoded:
        assert decoded.format == "WEBP"
        assert decoded.size == (160, 120)
        assert not decoded.getexif()
        assert int(getattr(decoded, "n_frames", 1)) == 1


def test_heic_photo_is_reencoded_as_static_webp_without_metadata() -> None:
    prepared = _prepare_message_image(
        UploadedMessageImage(
            data=_image_bytes("HEIF"),
            filename="iphone-photo.heic",
            content_type="image/heic",
        )
    )

    assert prepared.content_type == "image/webp"
    assert prepared.data[:4] == b"RIFF"
    with Image.open(io.BytesIO(prepared.data)) as decoded:
        assert decoded.format == "WEBP"
        assert decoded.size == (160, 120)
        assert not decoded.getexif()


def test_invalid_file_cannot_bypass_validation_with_image_mime() -> None:
    with pytest.raises(MessageImageError, match="valid image") as caught:
        _prepare_message_image(
            UploadedMessageImage(data=b"<script>alert(1)</script>", content_type="image/png")
        )

    assert caught.value.code == "invalid_image"


def test_image_pixel_bomb_is_rejected_before_full_decode() -> None:
    with pytest.raises(MessageImageError) as caught:
        _prepare_message_image(
            UploadedMessageImage(data=_image_bytes("PNG", (5000, 4000)), content_type="image/png")
        )

    assert caught.value.code == "image_dimensions"


def test_content_addressed_storage_reuses_identical_webp(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(message_image_service, "MESSAGE_IMAGE_DIR", tmp_path)
    prepared = _prepare_message_image(
        UploadedMessageImage(data=_image_bytes("PNG"), content_type="image/png")
    )

    first = _write_image_atomically(prepared)
    second = _write_image_atomically(prepared)

    assert first == second
    assert first.read_bytes() == prepared.data
    first.write_bytes(b"corrupt")
    assert _write_image_atomically(prepared).read_bytes() == prepared.data
    assert list(tmp_path.rglob("*.webp")) == [first]
