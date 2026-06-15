from types import SimpleNamespace

from bot.services.email_auth_service import EmailAuthService
from bot.services.email_templates import EmailInlineImage


def _settings():
    return SimpleNamespace(
        SMTP_FROM_NAME="Mini Shop",
        SMTP_FROM_EMAIL="noreply@example.com",
        WEBAPP_TITLE="Mini Shop",
    )


def test_build_email_message_attaches_inline_images_to_html_part():
    service = EmailAuthService(_settings())

    message = service._build_email_message(
        email="user@example.com",
        subject="Login code",
        body="Your code: 123456",
        html_body='<img src="cid:webapp-logo@remnawave-minishop" alt="">',
        inline_images=(
            EmailInlineImage(
                content_id="webapp-logo@remnawave-minishop",
                content_type="image/png",
                data=b"\x89PNG\r\n\x1a\nlogo",
            ),
        ),
    )

    related_part = message.get_body(("related",))
    assert related_part is not None
    html_part = related_part.get_body(("html",))
    assert html_part is not None
    related_images = [part for part in related_part.iter_attachments()]

    assert len(related_images) == 1
    assert related_images[0].get_content_type() == "image/png"
    assert related_images[0]["Content-ID"] == "<webapp-logo@remnawave-minishop>"
    assert related_images[0].get_content_disposition() == "inline"
    assert related_images[0].get_filename() == "webapp-logo-remnawave-minishop.png"
