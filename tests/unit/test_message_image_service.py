from __future__ import annotations

import asyncio
import io

import pytest
from PIL import Image

from bot.services import message_image_service
from bot.services.message_image_service import (
    MESSAGE_IMAGE_CONTENT_TYPE,
    MESSAGE_IMAGE_OUTPUT_MAX_BYTES,
    MessageImageError,
    StoredMessageImage,
    UploadedMessageImage,
    _prepare_message_image,
    _write_image_atomically,
)
from bot.services.message_image_telegram import prepare_telegram_photo


def _image_bytes(format_name: str, size: tuple[int, int] = (160, 120)) -> bytes:
    output = io.BytesIO()
    exif = Image.Exif()
    exif[0x010E] = "ignored metadata"
    Image.new("RGB", size, (32, 96, 180)).save(output, format=format_name, exif=exif)
    return output.getvalue()


@pytest.mark.parametrize("format_name", ["JPEG", "PNG", "WEBP", "HEIF"])
def test_uploaded_image_is_reencoded_as_static_webp_without_metadata(format_name: str) -> None:
    prepared = _prepare_message_image(
        UploadedMessageImage(
            data=_image_bytes(format_name),
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

    photo = asyncio.run(prepare_telegram_photo(prepared))
    assert photo.filename is not None and photo.filename.endswith(".jpg")
    assert len(photo.data) <= MESSAGE_IMAGE_OUTPUT_MAX_BYTES
    with Image.open(io.BytesIO(photo.data)) as decoded:
        assert decoded.format == "JPEG"
        assert decoded.mode == "RGB"
        assert decoded.size == (160, 120)
        assert not decoded.getexif()
        assert not decoded.info.get("icc_profile")


@pytest.mark.parametrize("mode", ["RGBA", "LA", "P"])
def test_transparent_png_is_sent_as_opaque_photo(mode: str) -> None:
    source = Image.new("RGBA", (160, 120), (0, 0, 0, 0))
    source.paste((0, 0, 0, 128), (40, 30, 120, 90))
    output = io.BytesIO()
    source.convert(mode).save(output, format="PNG")
    prepared = _prepare_message_image(
        UploadedMessageImage(data=output.getvalue(), filename="transparent.png")
    )

    photo = asyncio.run(prepare_telegram_photo(prepared))

    with Image.open(io.BytesIO(photo.data)) as decoded:
        assert decoded.format == "JPEG"
        assert decoded.mode == "RGB"
        assert decoded.getpixel((0, 0)) == (255, 255, 255)
        center = decoded.getpixel((80, 60))
        assert isinstance(center, tuple)
        assert all(120 <= channel <= 135 for channel in center)


@pytest.mark.parametrize("size", [(2560, 50), (50, 2560), (2560, 1), (1, 2560)])
def test_telegram_photo_pads_extreme_aspect_ratios(size: tuple[int, int]) -> None:
    prepared = _prepare_message_image(UploadedMessageImage(data=_image_bytes("PNG", size)))

    photo = asyncio.run(prepare_telegram_photo(prepared))

    with Image.open(io.BytesIO(photo.data)) as decoded:
        assert max(decoded.size) <= 20 * min(decoded.size)
        assert decoded.width + decoded.height <= 10_000
        assert decoded.width >= prepared.width
        assert decoded.height >= prepared.height
        assert decoded.getpixel((0, 0)) == (255, 255, 255)


@pytest.mark.parametrize("format_name", ["GIF", "BMP", "TIFF"])
def test_unsupported_raster_formats_are_rejected_even_with_png_filename(format_name: str) -> None:
    with pytest.raises(MessageImageError) as caught:
        _prepare_message_image(
            UploadedMessageImage(
                data=_image_bytes(format_name), filename="photo.png", content_type="image/png"
            )
        )

    assert caught.value.code == "unsupported_image"


@pytest.mark.parametrize("format_name", ["PNG", "WEBP"])
def test_animated_images_are_rejected(format_name: str) -> None:
    output = io.BytesIO()
    Image.new("RGB", (160, 120), "red").save(
        output,
        format=format_name,
        save_all=True,
        append_images=[Image.new("RGB", (160, 120), "blue")],
        duration=100,
        loop=0,
    )

    with pytest.raises(MessageImageError) as caught:
        _prepare_message_image(UploadedMessageImage(data=output.getvalue()))

    assert caught.value.code == "animated_image"


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


@pytest.mark.parametrize(
    ("format_name", "filename", "content_type"),
    [
        ("JPEG", "iphone-photo.jpg", "image/jpg"),
        ("HEIF", "iphone-photo.jpg", "image/jpeg"),
        ("HEIF", "iphone-photo", "image/x-heic"),
    ],
)
def test_ios_mime_and_filename_mismatches_are_validated_by_content(
    format_name: str,
    filename: str,
    content_type: str,
) -> None:
    prepared = _prepare_message_image(
        UploadedMessageImage(
            data=_image_bytes(format_name),
            filename=filename,
            content_type=content_type,
        )
    )

    assert prepared.content_type == "image/webp"
    assert prepared.filename.endswith(".webp")


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


def test_stored_webp_is_preserved_and_checked_when_preparing_telegram_photo(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(message_image_service, "MESSAGE_IMAGE_DIR", tmp_path)
    prepared = _prepare_message_image(UploadedMessageImage(data=_image_bytes("PNG")))
    path = _write_image_atomically(prepared)
    stored = StoredMessageImage(
        image_id="1" * 32,
        digest=prepared.digest,
        filename=prepared.filename,
        content_type=prepared.content_type,
        size_bytes=prepared.size_bytes,
        width=prepared.width,
        height=prepared.height,
        path=path,
    )

    photo = asyncio.run(prepare_telegram_photo(stored))

    assert photo.data == asyncio.run(prepare_telegram_photo(prepared)).data
    assert path.read_bytes() == prepared.data
    path.write_bytes(b"corrupt")
    with pytest.raises(MessageImageError) as caught:
        asyncio.run(prepare_telegram_photo(stored))
    assert caught.value.code == "image_corrupt"
