from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

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
