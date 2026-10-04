import pytest

from bot.services.message_composition import MessageButton
from bot.services.support_message_body import (
    BODY_FORMAT_HTML,
    BODY_FORMAT_TEXT,
    SupportBodyError,
    normalize_body_format,
    sanitize_support_body,
    support_body_plain_text,
    support_body_telegram_html,
)
from bot.services.support_message_buttons import (
    decode_support_buttons,
    encode_support_buttons,
    support_buttons_payload,
)


def sanitize(body: str, *, max_length: int = 4000) -> str:
    stored, stored_format = sanitize_support_body(
        body, body_format=BODY_FORMAT_HTML, max_length=max_length
    )
    assert stored_format == BODY_FORMAT_HTML
    return str(stored)


def test_unknown_format_falls_back_to_plain_text():
    assert normalize_body_format("markdown") == BODY_FORMAT_TEXT
    assert normalize_body_format(None) == BODY_FORMAT_TEXT
    assert normalize_body_format("HTML") == BODY_FORMAT_HTML


def test_plain_body_keeps_its_characters_literal():
    stored, stored_format = sanitize_support_body(
        "  price < 5 & <b>not bold</b>  ",
        body_format=BODY_FORMAT_TEXT,
        max_length=4000,
    )

    assert stored == "price < 5 & <b>not bold</b>"
    assert stored_format == BODY_FORMAT_TEXT


def test_allowed_markup_survives_and_aliases_are_normalized():
    assert sanitize("<strong>bold</strong> and <em>italic</em>") == "<b>bold</b> and <i>italic</i>"


def test_disallowed_tags_lose_markup_but_keep_their_text():
    assert sanitize("<script>alert(1)</script>") == "alert(1)"
    assert sanitize("<span style='x'>plain</span>") == "plain"


def test_text_is_escaped_so_it_cannot_reopen_markup():
    assert sanitize("5 < 6 & 7 > 2") == "5 &lt; 6 &amp; 7 &gt; 2"


def test_links_keep_only_schemes_a_customer_can_be_told_to_open():
    assert sanitize('<a href="https://x.dev">open</a>') == '<a href="https://x.dev">open</a>'
    assert sanitize('<a href="javascript:alert(1)">click</a>') == "click"
    assert sanitize('<a href="/relative">click</a>') == "click"


def test_unclosed_and_crossed_markup_is_closed_in_order():
    assert sanitize("<b>bold") == "<b>bold</b>"
    assert sanitize("<b>one<i>two</b>three</i>") == "<b>one<i>two</i></b>three"


def test_block_tags_become_blank_lines():
    assert sanitize("<p>one</p><p>two</p>") == "one\n\ntwo"
    assert sanitize("one<br>two") == "one\ntwo"


def test_pre_keeps_its_content_literal():
    assert sanitize("<pre>a <b>b</b></pre>") == "<pre>a b</pre>"


def test_custom_emoji_survives_storage_and_telegram_with_plain_text_fallback():
    body = '<b>Files <tg-emoji emoji-id="5368651601797984900">📁</tg-emoji></b>'
    assert sanitize(body) == body
    assert support_body_telegram_html(body, "html") == body
    assert support_body_plain_text(body, "html") == "Files 📁"


@pytest.mark.parametrize(
    "body",
    [
        '<tg-emoji emoji-id="0">📁</tg-emoji>',
        '<tg-emoji emoji-id="123" onclick="bad()">📁</tg-emoji>',
        '<tg-emoji emoji-id="123"><b>📁</b></tg-emoji>',
        '<tg-emoji emoji-id="123"><tg-emoji emoji-id="456">📁</tg-emoji></tg-emoji>',
        '<tg-emoji emoji-id="123">📁',
    ],
)
def test_invalid_custom_emoji_keeps_only_safe_fallback(body):
    assert sanitize(body) == "📁"


@pytest.mark.parametrize("tag", ["code", "pre"])
def test_custom_emoji_is_plain_inside_code(tag):
    assert (
        sanitize(f'<{tag}><tg-emoji emoji-id="123">📁</tg-emoji></{tag}>') == f"<{tag}>📁</{tag}>"
    )


def test_custom_emoji_truncation_never_splits_unicode_sequence():
    body = '<b>x<tg-emoji emoji-id="123">👩🏽‍💻</tg-emoji>y</b>'
    assert sanitize(body, max_length=3) == "<b>x</b>…"
    assert sanitize(body, max_length=5) == '<b>x<tg-emoji emoji-id="123">👩🏽‍💻</tg-emoji></b>…'


def test_custom_emoji_markup_is_literal_in_old_plain_text_messages():
    body = '<tg-emoji emoji-id="123">📁</tg-emoji>'
    assert (
        support_body_telegram_html(body, "text")
        == '&lt;tg-emoji emoji-id="123"&gt;📁&lt;/tg-emoji&gt;'
    )


def test_truncation_cuts_visible_text_and_closes_tags():
    stored = sanitize("<b>abcdefghij</b>", max_length=4)

    assert stored == "<b>abcd</b>…"


def test_the_limit_counts_visible_characters_not_markup():
    stored = sanitize("<b>abcd</b>", max_length=4)

    assert stored == "<b>abcd</b>"


def test_a_body_that_sanitizes_to_nothing_is_rejected():
    with pytest.raises(SupportBodyError):
        sanitize("<span>   </span>")
    with pytest.raises(SupportBodyError):
        sanitize_support_body("   ", body_format=BODY_FORMAT_TEXT, max_length=4000)


def test_plain_text_rendering_drops_markup_for_email_previews():
    assert support_body_plain_text("<b>hi</b> <a href='https://x.dev'>x</a>", "html") == "hi x"
    assert support_body_plain_text("&lt;b&gt;", "html") == "<b>"


def test_plain_text_rendering_truncates_a_legacy_body():
    assert support_body_plain_text("abcdef", "text", limit=3) == "ab…"


def test_telegram_rendering_escapes_a_legacy_body_exactly_once():
    assert support_body_telegram_html("a < b", "text") == "a &lt; b"
    assert support_body_telegram_html("<b>x</b>", "html") == "<b>x</b>"


def test_buttons_round_trip_through_storage():
    encoded = encode_support_buttons(
        [
            MessageButton(
                label="Use the code",
                url="https://t.me/bot?startapp=promo_SAVE",
                kind="promo_webapp",
                promo_code="SAVE",
                telegram_web_app_url="https://app.example/?startapp=promo_SAVE",
            )
        ]
    )

    decoded = decode_support_buttons(encoded)

    assert [button.promo_code for button in decoded] == ["SAVE"]
    assert decoded[0].telegram_web_app_url == "https://app.example/?startapp=promo_SAVE"
    assert support_buttons_payload(encoded)[0]["url"] == "https://t.me/bot?startapp=promo_SAVE"


def test_stored_buttons_that_no_longer_parse_degrade_to_none():
    assert encode_support_buttons([]) is None
    assert decode_support_buttons(None) == []
    assert decode_support_buttons("not json") == []
    assert decode_support_buttons('[{"label": "x", "url": "", "kind": "url"}]') == []
    assert decode_support_buttons('[{"label": "x", "url": "https://x", "kind": "nope"}]') == []
