import asyncio
import json
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from pydantic import ValidationError

from bot.app.web.admin_api_impl import users_merge
from bot.app.web.admin_api_impl import users_merge_context as merge_context
from bot.app.web.admin_api_impl.users_detail import _user_search_condition
from db.dal.user_merge_dal import UserMergeConflictError


@pytest.fixture
def merge_case(monkeypatch):
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.execute = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    source = SimpleNamespace(user_id=-10, panel_user_uuid="source-panel")
    target = SimpleNamespace(user_id=42, panel_user_uuid="target-panel")
    body = users_merge.AdminUserMergeBody(source_user_id=-10, confirmation_user_id=42)
    request = cast(
        web.Request,
        SimpleNamespace(
            match_info={"user_id": "42"},
            app={"settings": SimpleNamespace(), "async_session_factory": lambda: session},
        ),
    )
    monkeypatch.setattr(users_merge, "_require_admin_user_id", MagicMock(return_value=100))
    monkeypatch.setattr(users_merge, "parse_body_or_400", AsyncMock(return_value=body))
    monkeypatch.setattr(users_merge, "is_admin", AsyncMock(return_value=True))
    monkeypatch.setattr(users_merge.user_dal, "lock_user_by_id", AsyncMock())
    monkeypatch.setattr(
        users_merge.user_dal, "get_user_by_id", AsyncMock(side_effect=[source, target])
    )
    merge = AsyncMock(return_value=target)
    monkeypatch.setattr(users_merge, "_merge_users_for_web", merge)
    monkeypatch.setattr(
        users_merge,
        "_build_account_merge_notice",
        AsyncMock(return_value={"final_end_date": "2030-01-01T00:00:00+00:00"}),
    )
    monkeypatch.setattr(
        users_merge, "_sync_merged_panel_identity_for_user", AsyncMock(return_value=True)
    )
    audit = AsyncMock()
    monkeypatch.setattr(users_merge.message_log_dal, "create_message_log_no_commit", audit)
    invalidate = AsyncMock()
    monkeypatch.setattr(users_merge, "_invalidate_after_admin_user_mutation", invalidate)
    return SimpleNamespace(
        request=request, session=session, merge=merge, audit=audit, body=body, invalidate=invalidate
    )


def test_manual_merge_uses_shared_rules_and_records_actor_in_same_transaction(
    merge_case,
) -> None:
    response = asyncio.run(users_merge.admin_user_merge_route(merge_case.request))
    payload = json.loads(response.text)
    assert response.status == 200
    assert payload == {
        "ok": True,
        "user_id": 42,
        "source_user_id": -10,
        "panel_reconciliation_pending": False,
        "final_end_date": "2030-01-01T00:00:00+00:00",
    }
    assert merge_case.merge.await_args.kwargs == {
        "source_user_id": -10,
        "target_user_id": 42,
        "reason": "admin_manual_merge:100",
        "send_user_email": True,
    }
    assert merge_case.audit.await_args.args[1]["user_id"] == 100
    merge_case.session.commit.assert_awaited_once()
    assert [call.args[1] for call in merge_case.invalidate.await_args_list] == [-10, 42]


@pytest.mark.parametrize(
    "source,confirmation,actor,code",
    [
        (42, 42, 100, "account_merge_not_required"),
        (-10, -10, 100, "account_merge_confirmation_required"),
        (-10, 42, -10, "account_merge_privileged_source"),
        (-10, 42, 42, "account_merge_privileged_source"),
    ],
)
def test_invalid_merge_never_mutates_accounts(
    merge_case, monkeypatch, source, confirmation, actor, code
) -> None:
    monkeypatch.setattr(
        users_merge,
        "parse_body_or_400",
        AsyncMock(
            return_value=users_merge.AdminUserMergeBody(
                source_user_id=source, confirmation_user_id=confirmation
            )
        ),
    )
    monkeypatch.setattr(users_merge, "_require_admin_user_id", MagicMock(return_value=actor))
    response = asyncio.run(users_merge.admin_user_merge_route(merge_case.request))
    assert json.loads(response.text)["error"] == code
    merge_case.merge.assert_not_awaited()
    merge_case.session.commit.assert_not_awaited()


@pytest.mark.parametrize("history", [False, True])
def test_protected_accounts_and_role_history_cannot_merge(merge_case, history) -> None:
    merge_case.session.scalar.side_effect = [None, 1] if history else [42, None]
    response = asyncio.run(users_merge.admin_user_merge_route(merge_case.request))
    assert response.status == 409
    merge_case.merge.assert_not_awaited()


def test_revoked_administrator_is_rechecked_under_role_lock(merge_case, monkeypatch) -> None:
    monkeypatch.setattr(users_merge, "is_admin", AsyncMock(return_value=False))
    response = asyncio.run(users_merge.admin_user_merge_route(merge_case.request))
    assert response.status == 403
    merge_case.merge.assert_not_awaited()


def test_removed_source_is_not_merged_again(merge_case, monkeypatch) -> None:
    monkeypatch.setattr(
        users_merge.user_dal, "get_user_by_id", AsyncMock(side_effect=[None, MagicMock()])
    )
    response = asyncio.run(users_merge.admin_user_merge_route(merge_case.request))
    assert response.status == 404
    merge_case.merge.assert_not_awaited()
    merge_case.session.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "code",
    [
        "account_merge_telegram_conflict",
        "account_merge_provider_conflict",
        "account_merge_duplicate_promo_conflict",
        "account_merge_conflict",
    ],
)
def test_shared_merge_conflicts_roll_back_and_do_not_reconcile(merge_case, code) -> None:
    merge_case.merge.side_effect = UserMergeConflictError("Conflict", code=code)
    response = asyncio.run(users_merge.admin_user_merge_route(merge_case.request))
    assert response.status == 409
    assert json.loads(response.text)["error"] == code
    merge_case.session.rollback.assert_awaited_once()
    merge_case.session.commit.assert_not_awaited()
    merge_case.audit.assert_not_awaited()


def test_panel_and_cache_failures_do_not_turn_committed_merge_into_retry(
    merge_case, monkeypatch
) -> None:
    monkeypatch.setattr(
        users_merge,
        "_sync_merged_panel_identity_for_user",
        AsyncMock(side_effect=RuntimeError("offline")),
    )
    merge_case.invalidate.side_effect = RuntimeError("cache offline")
    response = asyncio.run(users_merge.admin_user_merge_route(merge_case.request))
    assert response.status == 200
    assert json.loads(response.text)["panel_reconciliation_pending"] is True
    merge_case.session.commit.assert_awaited_once()
    merge_case.session.rollback.assert_not_awaited()


@pytest.mark.parametrize("value", [True, 42.5, "42"])
def test_account_identifiers_are_strict_integers(value) -> None:
    with pytest.raises(ValidationError):
        users_merge.AdminUserMergeBody.model_validate(
            {"source_user_id": value, "confirmation_user_id": 42}
        )


@pytest.fixture
def context_case(monkeypatch):
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.scalar = AsyncMock(side_effect=[None, None, 2])
    identity = SimpleNamespace(
        provider="google",
        email="login@example.test",
        email_verified=True,
        display_name="Customer",
        subject="must-not-be-exposed",
    )
    identities = MagicMock()
    identities.scalars.return_value.all.return_value = [identity]
    emails = MagicMock()
    emails.scalars.return_value.all.return_value = ["extra@example.test", "main@example.test"]
    session.execute = AsyncMock(side_effect=[identities, emails])
    user = SimpleNamespace(
        user_id=-10,
        email="main@example.test",
        email_verified_at=True,
        is_banned=False,
        password_hash="must-not-be-exposed",
    )
    get_user = AsyncMock(return_value=user)
    monkeypatch.setattr(merge_context.user_dal, "get_user_by_id", get_user)
    monkeypatch.setattr(merge_context, "_require_admin_user_id", MagicMock(return_value=100))
    request = cast(
        web.Request,
        SimpleNamespace(
            match_info={"user_id": "-10"},
            app={"async_session_factory": lambda: session},
        ),
    )
    return SimpleNamespace(request=request, session=session, user=user, get_user=get_user)


def test_merge_context_shows_credentials_without_secrets_and_is_not_cached(context_case) -> None:
    response = asyncio.run(merge_context.admin_user_merge_context_route(context_case.request))
    assert response.status == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert json.loads(response.text) == {
        "ok": True,
        "user_id": -10,
        "auth_identities": [
            {
                "provider": "google",
                "email": "login@example.test",
                "email_verified": True,
                "display_name": "Customer",
            }
        ],
        "verified_emails": ["extra@example.test", "main@example.test"],
        "passkey_count": 2,
        "password_available": True,
        "merge_eligibility": {"allowed": True, "reason": None},
    }
    context_case.session.commit.assert_not_called()
    queries = [str(call.args[0]) for call in context_case.session.scalar.await_args_list]
    assert "account_role_events.actor_user_id" in queries[1]
    assert "revoked_at" not in queries[0]


@pytest.mark.parametrize(
    "role,event,banned,actor,reason",
    [
        (-10, None, False, 100, "account_merge_privileged_source"),
        (None, 123, False, 100, "account_merge_privileged_source"),
        (None, None, True, 100, "account_merge_banned"),
        (None, None, False, -10, "account_merge_current_admin"),
    ],
)
def test_merge_context_explains_participant_restrictions(
    context_case, monkeypatch, role, event, banned, actor, reason
) -> None:
    context_case.session.scalar.side_effect = [role, event, 0]
    context_case.user.is_banned = banned
    monkeypatch.setattr(merge_context, "_require_admin_user_id", MagicMock(return_value=actor))
    response = asyncio.run(merge_context.admin_user_merge_context_route(context_case.request))
    assert json.loads(response.text)["merge_eligibility"] == {"allowed": False, "reason": reason}


def test_merge_context_for_deleted_account_does_not_return_stale_information(context_case) -> None:
    context_case.get_user.return_value = None
    response = asyncio.run(merge_context.admin_user_merge_context_route(context_case.request))
    assert response.status == 404
    context_case.session.scalar.assert_not_awaited()
    context_case.session.execute.assert_not_awaited()


def test_merge_context_requires_admin_before_loading_credentials(context_case, monkeypatch) -> None:
    monkeypatch.setattr(
        merge_context, "_require_admin_user_id", MagicMock(side_effect=web.HTTPForbidden())
    )
    with pytest.raises(web.HTTPForbidden):
        asyncio.run(merge_context.admin_user_merge_context_route(context_case.request))
    context_case.get_user.assert_not_awaited()


@pytest.mark.parametrize("query", ["-10", "42", "  @-10  "])
def test_shared_candidate_search_can_find_signed_internal_and_telegram_ids(query) -> None:
    condition = _user_search_condition(query)
    assert condition is not None
    sql = str(condition.compile(compile_kwargs={"literal_binds": True}))
    expected = int(query.strip().lstrip("@"))
    assert f"users.user_id = {expected}" in sql
    assert f"users.telegram_id = {expected}" in sql
    for field in ("username", "first_name", "last_name", "email", "minishop_id", "panel_username"):
        assert f"users.{field}" in sql


@pytest.mark.parametrize("query", ["--10", "9999999999999999999", "9" * 5000])
def test_candidate_search_never_binds_invalid_or_out_of_range_bigint(query) -> None:
    condition = _user_search_condition(query)
    assert condition is not None
    sql = str(condition)
    assert "users.user_id =" not in sql
    assert "users.telegram_id =" not in sql
