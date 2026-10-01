import json
from html.parser import HTMLParser
from types import SimpleNamespace

from bot.app.web.webapp.assets_theme import _initial_theme_for_request
from bot.app.web.webapp.html_payload import image_preload_markup, json_script_payload
from config.webapp_themes_config import builtin_webapp_themes_config


def test_logo_preload_cannot_create_attributes_or_elements() -> None:
    tags: list[tuple[str, list[tuple[str, str | None]]]] = []

    class Parser(HTMLParser):
        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            tags.append((tag, attrs))

    url = '/logo.png" onload="alert(1)"><meta http-equiv="refresh" content="0;url=/evil">'
    Parser().feed(image_preload_markup(url))
    assert len(tags) == 1
    assert tags[0][0] == "link"
    attrs = dict(tags[0][1])
    assert attrs["href"] == url
    assert set(attrs) == {"rel", "href", "as", "fetchpriority"}


def test_json_remains_data_even_with_html_end_tags() -> None:
    payload = {"title": '</script><meta http-equiv="refresh">', "ru": "Текст < & >"}
    encoded = json_script_payload(payload)
    assert "<" not in encoded
    assert json.loads(encoded) == payload


def test_initial_theme_is_identical_with_or_without_a_preview_link() -> None:
    catalog = builtin_webapp_themes_config("#abcdef")
    ordinary = _initial_theme_for_request(SimpleNamespace(query={}), catalog)
    preview = _initial_theme_for_request(
        SimpleNamespace(query={"theme_preview": "windows95"}), catalog
    )
    assert preview == ordinary
