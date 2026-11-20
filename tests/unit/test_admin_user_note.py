import asyncio
import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from bot.app.web.admin_api_impl import user_note


@pytest.mark.parametrize(
    ("existing", "previous", "draft", "status"),
    [
        ("old", "old", "new\nline", 200),
        ("old", "old", "", 200),
        ("other", "old", "new", 409),
        ("new", "old", "new", 200),
    ],
)
def test_put_note_compares_fresh_panel_value_and_writes_only_description(
    monkeypatch: pytest.MonkeyPatch,
    existing: str,
    previous: str,
    draft: str,
    status: int,
) -> None:
    session = AsyncMock()
    session.__aenter__.return_value = session
    ref = AsyncMock(return_value="154")
    panel = SimpleNamespace(
        get_user_by_uuid_lookup=AsyncMock(
            return_value={"ok": True, "user": {"description": existing}}
        ),
        update_user_details_on_panel=AsyncMock(return_value={"description": draft or None}),
    )
    audit = AsyncMock()
    monkeypatch.setattr(user_note, "_require_admin_user_id", lambda _: 5)
    monkeypatch.setattr(user_note, "linked_panel_account", ref)
    monkeypatch.setattr(
        user_note,
        "parse_body_or_400",
        AsyncMock(return_value=user_note.AdminUserNoteBody(note=draft, previous_note=previous)),
    )
    monkeypatch.setattr(user_note.message_log_dal, "create_message_log_no_commit", audit)
    monkeypatch.setattr(user_note, "_invalidate_after_admin_user_mutation", AsyncMock())
    request = cast(
        Any,
        SimpleNamespace(
            match_info={"user_id": "73"},
            app={
                "panel_service": panel,
                "async_session_factory": lambda: session,
                "settings": object(),
            },
        ),
    )
    response = asyncio.run(user_note.admin_user_note_put_route(request))
    assert response.status == status
    ref.assert_awaited_once_with(session, 73, lock=True)
    panel.get_user_by_uuid_lookup.assert_awaited_once_with("154")
    if status == 409 or existing == draft:
        panel.update_user_details_on_panel.assert_not_awaited()
        audit.assert_not_awaited()
    else:
        panel.update_user_details_on_panel.assert_awaited_once_with(
            "154", {"description": draft or None}
        )
        assert json.loads(response.text or "{}")["note"] == draft
        assert audit.await_args is not None
        assert audit.await_args.args[1]["target_user_id"] == 73
        session.commit.assert_awaited_once()
