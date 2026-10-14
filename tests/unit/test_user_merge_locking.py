from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from sqlalchemy.dialects import postgresql

from db.dal import user_merge_dal


class _ListResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


class UserMergeLockingTests(IsolatedAsyncioTestCase):
    async def test_lock_users_for_merge_uses_stable_row_locks(self):
        source = SimpleNamespace(user_id=7)
        target = SimpleNamespace(user_id=42)
        session = SimpleNamespace(execute=AsyncMock(return_value=_ListResult([target, source])))

        locked_source, locked_target = await user_merge_dal._lock_users_for_merge(session, 7, 42)

        self.assertIs(locked_source, source)
        self.assertIs(locked_target, target)
        stmt = session.execute.await_args.args[0]
        sql = str(
            stmt.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).upper()
        self.assertIn("USERS.USER_ID IN (7, 42)", sql)
        self.assertIn("ORDER BY USERS.USER_ID", sql)
        self.assertIn("FOR UPDATE", sql)

    async def test_merge_rejects_banned_participants_before_side_effects(self):
        for source_banned, target_banned in ((True, False), (False, True), (True, True)):
            with self.subTest(source_banned=source_banned, target_banned=target_banned):
                source = SimpleNamespace(user_id=7, is_banned=source_banned)
                target = SimpleNamespace(user_id=42, is_banned=target_banned)
                session = SimpleNamespace(
                    execute=AsyncMock(),
                    delete=AsyncMock(),
                    flush=AsyncMock(),
                    refresh=AsyncMock(),
                )

                with (
                    patch.object(
                        user_merge_dal,
                        "_lock_users_for_merge",
                        AsyncMock(return_value=(source, target)),
                    ),
                    patch.object(
                        user_merge_dal,
                        "merge_promo_activation_history",
                        AsyncMock(),
                    ) as promo_check,
                    patch.object(
                        user_merge_dal,
                        "defer_event_until_commit",
                        Mock(),
                    ) as emit_model,
                    self.assertRaises(user_merge_dal.UserMergeConflictError) as raised,
                ):
                    await user_merge_dal.merge_users(
                        session,
                        source_user_id=7,
                        target_user_id=42,
                        reason="email_link",
                    )

                self.assertEqual(raised.exception.message_key, "wa_auth_access_denied")
                promo_check.assert_not_awaited()
                session.execute.assert_not_awaited()
                session.delete.assert_not_awaited()
                session.flush.assert_not_awaited()
                emit_model.assert_not_called()
