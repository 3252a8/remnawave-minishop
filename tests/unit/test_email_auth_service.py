import unittest
from email.utils import parsedate_to_datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

from sqlalchemy.dialects import postgresql

from bot.services.email_auth_service import EmailAuthService
from bot.services.email_templates import EmailInlineImage
from db.dal import security_dal


def _settings():
    return SimpleNamespace(
        SMTP_FROM_NAME="Mini Shop",
        SMTP_FROM_EMAIL="noreply@example.com",
        WEBAPP_TITLE="Mini Shop",
        SUBSCRIPTION_MINI_APP_URL="https://app.example.com/",
        BOT_TOKEN="bot-token",
    )


def test_build_magic_link_includes_referral_param():
    service = EmailAuthService(_settings())

    link = service._build_magic_link(
        token="login-token",
        purpose="login",
        referral_param="uABC123",
    )

    assert link is not None
    query = parse_qs(urlsplit(link).query)
    assert query["login_token"] == ["login-token"]
    assert query["ref"] == ["uABC123"]


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
    related_images = list(related_part.iter_attachments())

    assert len(related_images) == 1
    assert related_images[0].get_content_type() == "image/png"
    assert related_images[0]["Content-ID"] == "<webapp-logo@remnawave-minishop>"
    assert related_images[0].get_content_disposition() == "inline"
    assert related_images[0].get_filename() == "webapp-logo-remnawave-minishop.png"


def test_build_email_message_adds_rfc_delivery_headers():
    service = EmailAuthService(_settings())

    message = service._build_email_message(
        email="user@example.com",
        subject="Login code",
        body="Your code: 123456",
    )

    assert message["Message-ID"]
    assert message["Message-ID"].startswith("<")
    assert message["Message-ID"].endswith("@example.com>")
    assert parsedate_to_datetime(message["Date"]) is not None


class EmailAuthConsumptionLockTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _empty_result():
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    async def test_code_verification_locks_candidate_until_consumed(self):
        service = EmailAuthService(_settings())
        session = SimpleNamespace(execute=AsyncMock(return_value=self._empty_result()))

        with patch.object(
            security_dal,
            "check_throttle",
            AsyncMock(return_value=security_dal.ThrottleDecision(locked=False)),
        ):
            result = await service.verify_code(
                session,
                email="user@example.com",
                purpose="login",
                code="123456",
            )

        self.assertFalse(result.ok)
        statement = session.execute.await_args.args[0]
        rendered = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("FOR UPDATE", rendered)

    async def test_magic_link_verification_locks_candidate_until_consumed(self):
        service = EmailAuthService(_settings())
        session = SimpleNamespace(execute=AsyncMock(return_value=self._empty_result()))

        result = await service.verify_magic_token(
            session,
            token="magic-token",
            purpose="login",
        )

        self.assertFalse(result.ok)
        statement = session.execute.await_args.args[0]
        rendered = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("FOR UPDATE", rendered)
