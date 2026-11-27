import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from bot.plugins.builtin.blacklist import sources
from bot.plugins.builtin.blacklist.settings import (
    DEFAULT_SETTINGS,
    DEFAULT_SOURCES,
    SourceURLValidationError,
    validate_source_urls,
)
from bot.plugins.builtin.blacklist.sources import Reason, SourceError, merge_reasons, parse_source


def test_identical_download_skips_parsing(monkeypatch) -> None:
    content = b"42 # example"
    monkeypatch.setattr(sources, "_download", AsyncMock(return_value=content))
    snapshot = asyncio.run(sources.fetch_source("https://example.org/list", None))
    assert snapshot is not None and snapshot.entries == {42: (Reason("example"),)}
    parse = Mock(side_effect=AssertionError("unchanged source was parsed again"))
    monkeypatch.setattr(sources, "parse_source", parse)
    assert (
        asyncio.run(sources.fetch_source("https://example.org/list", snapshot.content_sha256))
        is None
    )
    parse.assert_not_called()


def test_source_defaults_and_url_deduplication() -> None:
    assert DEFAULT_SETTINGS.refresh_hours == 24
    assert validate_source_urls([*DEFAULT_SOURCES, f"  {DEFAULT_SOURCES[0]}  ", ""]) == (
        DEFAULT_SOURCES
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/list.txt",
        "https://localhost/list.txt",
        "https://127.0.0.1/list.txt",
        "https://[::ffff:127.0.0.1]/list.txt",
        "https://[64:ff9b::7f00:1]/list.txt",
        "https://user@example.org/list.txt",
        "https://example.org:0/list.txt",
        "https://example.org/list.txt#fragment",
    ],
)
def test_rejects_invalid_or_non_public_urls(url: str) -> None:
    with pytest.raises(SourceURLValidationError, match="invalid_source_url"):
        validate_source_urls([url])


def test_sources_preserve_distinct_comments_and_evidence() -> None:
    data = (
        "\ufeff# комментарий к файлу\r\n"
        " 42 # Первая причина https://t.me/report/1\r\n"
        "42 # Вторая # причина (https://t.me/report/2)\r\n"
        "42 # Первая причина <https://t.me/report/3> https://t.me/report/1\r\n"
        "43 # [Отчёт](https://example.org/report?record=43#details)\r\n"
        "44 # <https://t.me/report/4>\r\n"
        "45\r\n"
        "bad row\r\n"
        "0 # ID отсутствует\r\n"
        "9223372036854775808 # слишком большой ID\r\n"
    )
    result = parse_source(data.encode())

    assert result.invalid_lines == 3
    assert result.entries == {
        42: (
            Reason("Первая причина", ("https://t.me/report/1", "https://t.me/report/3")),
            Reason("Вторая # причина", ("https://t.me/report/2",)),
        ),
        43: (Reason("Отчёт", ("https://example.org/report?record=43#details",)),),
        44: (Reason("", ("https://t.me/report/4",)),),
        45: (),
    }
    other = parse_source("42 # Вторая # причина\n42 # Третья причина".encode())
    assert merge_reasons([result.entries[42], other.entries[42]]) == (
        *result.entries[42],
        Reason("Третья причина"),
    )


def test_empty_list_is_valid_but_html_cannot_replace_a_snapshot() -> None:
    assert parse_source(b"\n# empty list\n").entries == {}
    with pytest.raises(SourceError, match="source_invalid_format"):
        parse_source(b"<!doctype html>\n<html>Service is unavailable</html>")
    with pytest.raises(SourceError, match="source_invalid_encoding"):
        parse_source(b"42 # \xff")
