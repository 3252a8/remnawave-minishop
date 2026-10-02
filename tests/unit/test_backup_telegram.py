import asyncio
import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, create_autospec

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramEntityTooLarge, TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SendMediaGroup
from aiogram.types import FSInputFile, InputMediaDocument

from bot.services import backup_telegram
from bot.services.backup_parts import join_backup


def _send(tmp_path: Path, bot: Bot, payload: bytes) -> Path:
    archive = tmp_path / "backup.zip"
    archive.write_bytes(payload)
    asyncio.run(
        backup_telegram.send_backup_parts(
            bot,
            archive,
            chat_id=123,
            thread_id=77,
            caption="Backup details",
            language="ru",
            part_bytes=17,
        )
    )
    return archive


def test_album_parts_reassemble_into_original_zip_and_clean_up(tmp_path: Path) -> None:
    bot = create_autospec(Bot, instance=True)
    downloaded = tmp_path / "downloaded"
    downloaded.mkdir()

    async def capture(**kwargs: object) -> None:
        assert kwargs["chat_id"] == 123
        assert kwargs["message_thread_id"] == 77
        media = kwargs["media"]
        assert isinstance(media, list)
        assert len(media) == 4
        for document in media:
            assert isinstance(document, InputMediaDocument)
            assert isinstance(document.media, FSInputFile)
            assert document.parse_mode is None
            assert document.media.filename is not None
            await asyncio.to_thread(
                shutil.copyfile, document.media.path, downloaded / document.media.filename
            )

    bot.send_media_group.side_effect = capture
    archive = _send(tmp_path, bot, bytes(range(40)))
    bot.send_media_group.assert_awaited_once()
    bot.send_document.assert_not_awaited()
    result = join_backup(downloaded / "backup.zip.parts.json")
    assert result.read_bytes() == archive.read_bytes()
    assert list(tmp_path.glob("telegram-parts-*")) == []
    captions = [document.caption for document in bot.send_media_group.await_args.kwargs["media"]]
    assert "3 частей" in captions[0]
    assert "1/3" in captions[1]


def test_more_than_ten_documents_use_multiple_albums(tmp_path: Path) -> None:
    bot = create_autospec(Bot, instance=True)
    _send(tmp_path, bot, b"x" * (17 * 11))
    assert [len(call.kwargs["media"]) for call in bot.send_media_group.await_args_list] == [10, 2]
    bot.send_document.assert_not_awaited()


def test_single_remainder_is_sent_as_document(tmp_path: Path) -> None:
    bot = create_autospec(Bot, instance=True)
    _send(tmp_path, bot, b"x" * (17 * 10))
    assert len(bot.send_media_group.await_args.kwargs["media"]) == 10
    bot.send_document.assert_awaited_once()
    assert bot.send_document.await_args.kwargs["message_thread_id"] == 77


def test_oversized_album_falls_back_to_individual_files(tmp_path: Path) -> None:
    bot = create_autospec(Bot, instance=True)
    bot.send_media_group.side_effect = TelegramEntityTooLarge(
        method=SendMediaGroup(chat_id=123, media=[]), message="Request Entity Too Large"
    )
    archive = _send(tmp_path, bot, b"x" * 40)
    assert bot.send_media_group.await_count == 1
    assert bot.send_document.await_count == 4
    assert archive.is_file()
    assert list(tmp_path.glob("telegram-parts-*")) == []


@pytest.mark.parametrize("failure", ["network", "rate_limit"])
def test_only_failed_batch_is_retried(tmp_path: Path, monkeypatch, failure: str) -> None:
    bot = create_autospec(Bot, instance=True)
    method = SendMediaGroup(chat_id=123, media=[])
    error = (
        TelegramNetworkError(method=method, message="temporary connection failure")
        if failure == "network"
        else TelegramRetryAfter(method=method, message="Flood control", retry_after=1)
    )
    bot.send_media_group.side_effect = [None, error, None]
    monkeypatch.setattr(backup_telegram.asyncio, "sleep", AsyncMock())
    _send(tmp_path, bot, b"x" * (17 * 11))
    calls = bot.send_media_group.await_args_list
    assert [len(call.kwargs["media"]) for call in calls] == [10, 2, 2]
    assert calls[1].kwargs["media"] == calls[2].kwargs["media"]


def test_failure_reports_progress_retains_zip_and_removes_parts(tmp_path: Path) -> None:
    bot = create_autospec(Bot, instance=True)
    bot.send_media_group.side_effect = [None, RuntimeError("upload failed")]
    with pytest.raises(RuntimeError, match="10 из 12"):
        _send(tmp_path, bot, b"x" * (17 * 11))
    assert (tmp_path / "backup.zip").is_file()
    assert list(tmp_path.glob("telegram-parts-*")) == []


def test_manifest_and_parts_are_each_below_the_delivery_limit(tmp_path: Path) -> None:
    bot = create_autospec(Bot, instance=True)

    async def inspect(**kwargs: object) -> None:
        media = kwargs["media"]
        assert isinstance(media, list)
        for document in media:
            assert isinstance(document.media, FSInputFile)
            path = Path(document.media.path)
            if path.suffix == ".json":
                metadata = json.loads(await asyncio.to_thread(path.read_text))
                assert metadata["size_bytes"] == 35
            else:
                assert (await asyncio.to_thread(path.stat)).st_size <= 17

    bot.send_media_group.side_effect = inspect
    _send(tmp_path, bot, b"x" * 35)
