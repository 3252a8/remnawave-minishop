from html.parser import HTMLParser

from bot.app.web.webapp.html_payload import image_preload_markup


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
