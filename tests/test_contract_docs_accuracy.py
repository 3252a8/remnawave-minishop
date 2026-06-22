from __future__ import annotations

from bot.infra.event_catalog import DEFAULT_OUTPUT_PATH, generate_event_catalog_markdown


def test_event_catalog_doc_is_current():
    expected = DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
    actual = generate_event_catalog_markdown()

    assert actual == expected, (
        "Regenerate docs/architecture/events.md with "
        "PYTHONPATH=backend python -m bot.infra.event_catalog"
    )
