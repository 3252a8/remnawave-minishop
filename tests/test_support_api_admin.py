from bot.app.web.admin_api_impl.support import AdminTicketPatchPayload, AdminTicketReplyPayload


def test_admin_patch_payload_accepts_closed_status_and_urgent_priority():
    payload = AdminTicketPatchPayload.model_validate(
        {"status": "closed", "priority": "urgent", "category": "billing"}
    )

    assert payload.status == "closed"
    assert payload.priority == "urgent"


def test_admin_reply_payload_supports_internal_note():
    payload = AdminTicketReplyPayload.model_validate({"body": " note ", "is_internal_note": True})

    assert payload.body == "note"
    assert payload.is_internal_note is True
