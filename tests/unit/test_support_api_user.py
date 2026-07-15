import pytest
from pydantic import ValidationError

from bot.app.web.support_schemas import SupportTypingIn
from bot.app.web.webapp.payloads import CreateTicketPayload, TicketReplyPayload


def test_user_ticket_payload_accepts_only_public_priorities():
    payload = CreateTicketPayload.model_validate(
        {"subject": "Help", "category": "technical", "priority": "high", "body": "Text"}
    )

    assert payload.priority == "high"


def test_user_ticket_payload_rejects_admin_only_priority():
    with pytest.raises(ValidationError):
        CreateTicketPayload.model_validate(
            {"subject": "Help", "category": "technical", "priority": "urgent", "body": "Text"}
        )


def test_ticket_reply_trims_body():
    payload = TicketReplyPayload.model_validate({"body": "  hello  "})

    assert payload.body == "hello"


def test_ticket_typing_payload_is_boolean():
    payload = SupportTypingIn.model_validate({"typing": True})

    assert payload.typing is True
