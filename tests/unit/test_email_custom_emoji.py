import asyncio
import io
from email import policy
from email.parser import BytesParser
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from bot.services import email_custom_emoji as emoji_email
from bot.services.email_auth_service import EmailAuthService
from bot.services.email_templates import (
    EmailInlineImage,
    render_support_admin_reply_user,
    render_support_new_ticket_admin,
    render_support_user_reply_admin,
)
from bot.services.email_templates_common import _telegram_html_to_email_html
from bot.services.email_templates_notifications import render_broadcast_email
from bot.services.message_composition import MessageButton, email_links_for_buttons
from bot.services.telegram_emoji_catalog import TelegramEmojiError
from config.settings import Settings

FOLDER_ID = "5368651601797984900"
COMPUTER_ID = "5368584419919541454"


def _settings(**overrides):
    values = {
        "BOT_TOKEN": "123456:test",
        "POSTGRES_USER": "app_user",
        "POSTGRES_PASSWORD": "app_password",
        "SMTP_FROM_EMAIL": "noreply@example.com",
        "TELEGRAM_BOT_PROXY_URL": None,
        "TELEGRAM_BOT_API_BASE_URL": None,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _webp():
    buffer = io.BytesIO()
    Image.new("RGBA", (100, 100), (255, 80, 40, 255)).save(buffer, "WEBP")
    return buffer.getvalue()


@pytest.fixture
def previews(monkeypatch):
    bot = MagicMock()
    bot.context.return_value.__aenter__.return_value = bot
    factory = MagicMock(return_value=bot)
    monkeypatch.setattr(emoji_email, "create_telegram_bot", factory)
    resolve = AsyncMock(return_value=[])
    loader = AsyncMock(return_value=(_webp(), "image/webp"))
    monkeypatch.setattr(emoji_email, "resolve_ids", resolve)
    monkeypatch.setattr(emoji_email, "media", loader)
    return bot, factory, resolve, loader


def _converted(identifiers):
    return _telegram_html_to_email_html(
        " ".join(f'<tg-emoji emoji-id="{identifier}">📁</tg-emoji>' for identifier in identifiers)
    )


def test_email_button_custom_icon_uses_cid_without_rendering_caption_markup(previews):
    button = MessageButton(
        label='<img src="bad"> Files & folders',
        url="https://example.com",
        kind="url",
        icon_custom_emoji_id=FOLDER_ID,
        icon_emoji="📁",
    )
    settings = _settings()
    content = render_broadcast_email(
        settings,
        language_code="en",
        subject="Files",
        message_text="Hello",
        buttons=email_links_for_buttons([button]),
    )
    assert '<span data-telegram-emoji-id="' in content.html
    assert "&lt;img src=&quot;bad&quot;&gt; Files &amp; folders" in content.html
    assert '<img src="bad">' not in content.html
    assert '📁 <img src="bad"> Files & folders: https://example.com' in content.text
    assert "tg-emoji" not in content.text
    service = EmailAuthService(settings)
    service._send_custom_email_sync = MagicMock()
    asyncio.run(
        service.send_custom_email(
            email="owner@example.com",
            subject=content.subject,
            body=content.text,
            html_body=content.html,
            inline_images=content.inline_images,
        )
    )
    sent = service._send_custom_email_sync.call_args.kwargs
    assert f"cid:telegram-emoji-{FOLDER_ID}@remnawave-minishop" in sent["html_body"]
    assert any(
        image.content_id.startswith(f"telegram-emoji-{FOLDER_ID}")
        for image in sent["inline_images"]
    )
    assert "api.telegram.org" not in sent["html_body"]


def test_email_sender_embeds_png_cids_and_preserves_plain_text_and_other_images(previews):
    service = EmailAuthService(_settings())
    service._send_custom_email_sync = MagicMock()
    logo = EmailInlineImage("logo@example", "image/png", b"logo")
    source = _converted([FOLDER_ID, COMPUTER_ID, FOLDER_ID])
    asyncio.run(
        service.send_custom_email(
            email="owner@example.com",
            subject="Emoji",
            body="📁 📁 📁",
            html_body=source,
            inline_images=(logo,),
        )
    )
    kwargs = service._send_custom_email_sync.call_args.kwargs
    assert kwargs["body"] == "📁 📁 📁"
    assert kwargs["html_body"].count("<img ") == 3
    assert "data-telegram-emoji-id" not in kwargs["html_body"]
    assert "api.telegram.org" not in kwargs["html_body"]
    assert len(kwargs["inline_images"]) == 3
    assert kwargs["inline_images"][0] is logo
    message = service._build_email_message(**kwargs)
    parsed = BytesParser(policy=policy.default).parsebytes(message.as_bytes())
    assert parsed.get_body(("plain",)).get_content().strip() == "📁 📁 📁"
    html_body = parsed.get_body(("html",)).get_content()
    images = [part for part in parsed.walk() if part.get_content_maintype() == "image"]
    assert len(images) == 3
    for part in images[1:]:
        cid = str(part["Content-ID"]).strip("<>")
        assert f"cid:{cid}" in html_body
        assert part.get_content_type() == "image/png"
        assert part.get_content_disposition() == "inline"
        with Image.open(io.BytesIO(part.get_payload(decode=True))) as image:
            assert image.format == "PNG"
            assert image.size == (100, 100)
    previews[2].assert_awaited_once_with(previews[0], [FOLDER_ID, COMPUTER_ID])
    assert previews[3].await_count == 2
    previews[0].context.return_value.__aexit__.assert_awaited_once()


def test_complete_96_item_set_fits_in_one_email(previews):
    identifiers = [str(1000 + index) for index in range(96)]
    html_body, images = asyncio.run(
        emoji_email.prepare_email_custom_emoji(_settings(), _converted(identifiers), ())
    )
    assert html_body.count("<img ") == 96
    assert len(images) == 96
    previews[2].assert_awaited_once_with(previews[0], identifiers)


def test_emoji_failure_keeps_unicode_and_successful_images(previews):
    async def load(_bot, identifier):
        if identifier == COMPUTER_ID:
            raise TelegramEmojiError("telegram_emoji_preview_unavailable", 404)
        return _webp(), "image/webp"

    previews[3].side_effect = load
    html_body, images = asyncio.run(
        emoji_email.prepare_email_custom_emoji(
            _settings(), _converted([FOLDER_ID, COMPUTER_ID]), ()
        )
    )
    assert len(images) == 1
    assert html_body.count("<img ") == 1
    assert html_body.endswith("📁")
    assert "<span" not in html_body


@pytest.mark.parametrize("html_body", [None, "<strong>Hello</strong>", _converted([FOLDER_ID])])
def test_missing_bot_token_preserves_content_without_network(html_body, previews):
    prepared, images = asyncio.run(
        emoji_email.prepare_email_custom_emoji(
            _settings(BOT_TOKEN="", TELEGRAM_ENABLED=False), html_body, ()
        )
    )
    assert prepared == ("📁" if html_body and "data-telegram-emoji-id" in html_body else html_body)
    assert images == ()
    previews[1].assert_not_called()


def test_deadline_keeps_completed_images_and_cancels_pending_work(previews, monkeypatch):
    async def load(_bot, identifier):
        if identifier == COMPUTER_ID:
            await asyncio.sleep(1)
        return _webp(), "image/webp"

    previews[3].side_effect = load
    monkeypatch.setattr(emoji_email, "EMOJI_PREPARE_TIMEOUT", 0.05)
    html_body, images = asyncio.run(
        emoji_email.prepare_email_custom_emoji(
            _settings(), _converted([FOLDER_ID, COMPUTER_ID]), ()
        )
    )
    assert len(images) == 1
    assert html_body.count("<img ") == 1
    assert html_body.endswith("📁")
    previews[0].context.return_value.__aexit__.assert_awaited_once()


def test_unique_id_and_attachment_byte_limits_preserve_remaining_fallback(previews, monkeypatch):
    monkeypatch.setattr(emoji_email, "MAX_EMAIL_EMOJI", 2)
    monkeypatch.setattr(emoji_email, "MAX_EMAIL_EMOJI_BYTES", 1)
    html_body, images = asyncio.run(
        emoji_email.prepare_email_custom_emoji(_settings(), _converted(["1", "2", "3"]), ())
    )
    assert html_body == "📁 📁 📁"
    assert images == ()
    assert previews[3].await_count == 2


@pytest.mark.parametrize(
    ("content", "mime"),
    [(b"<svg onload='bad()'></svg>", "image/svg+xml"), (b"invalid", "image/png")],
)
def test_unsafe_or_invalid_media_is_unicode_fallback(content, mime, previews):
    previews[3].return_value = content, mime
    assert asyncio.run(
        emoji_email.prepare_email_custom_emoji(_settings(), _converted([FOLDER_ID]), ())
    ) == ("📁", ())


def test_untrusted_markup_cannot_forge_email_media_markers(previews):
    source = '<span data-telegram-emoji-id="123">📁</span><img src="https://evil.example/x">'
    converted = _telegram_html_to_email_html(source)
    html_body, images = asyncio.run(
        emoji_email.prepare_email_custom_emoji(_settings(), converted, ())
    )
    assert "<img" not in html_body
    assert images == ()
    previews[1].assert_not_called()


@pytest.mark.parametrize(
    "renderer",
    [
        render_support_new_ticket_admin,
        render_support_user_reply_admin,
        render_support_admin_reply_user,
    ],
)
def test_all_support_email_templates_keep_custom_emoji_and_formatting(renderer):
    extra = (
        {}
        if renderer is render_support_admin_reply_user
        else {
            "user_display": "Owner",
            "snapshot_rows": [],
        }
    )
    content = renderer(
        _settings(),
        None,
        "ru",
        ticket_id=7,
        subject="Files",
        body_preview="Files 📁",
        body_preview_html=f'<b>Files <tg-emoji emoji-id="{FOLDER_ID}">📁</tg-emoji></b>',
        ticket_url=None,
        **extra,
    )
    assert "Files 📁" in content.text
    assert "<tg-emoji" not in content.text
    assert f'data-telegram-emoji-id="{FOLDER_ID}"' in content.html
    assert "<strong>Files" in content.html
