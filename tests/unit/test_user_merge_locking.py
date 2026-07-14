from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy.dialects import postgresql

from db.dal import user_merge_dal


class _ListResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class UserMergeLockingTests(IsolatedAsyncioTestCase):
    async def test_duplicate_promo_check_compares_both_accounts(self):
        session = SimpleNamespace(execute=AsyncMock(return_value=_ScalarResult(99)))

        shared = await user_merge_dal._accounts_share_promo_activation(session, 7, 42)

        self.assertTrue(shared)
        stmt = session.execute.await_args.args[0]
        sql = str(
            stmt.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).upper()
        self.assertIn("PROMO_CODE_ACTIVATIONS.USER_ID = 7", sql)
        self.assertIn("PROMO_CODE_ACTIVATIONS.USER_ID = 42", sql)

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
                        "_accounts_share_promo_activation",
                        AsyncMock(),
                    ) as promo_check,
                    patch.object(
                        user_merge_dal.events,
                        "emit_model",
                        AsyncMock(),
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
                emit_model.assert_not_awaited()
