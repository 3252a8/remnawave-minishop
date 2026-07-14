from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy.dialects import postgresql

from db.dal import promo_code_dal, user_dal


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class UserEntitlementLockTests(IsolatedAsyncioTestCase):
    async def test_promo_consumption_locks_user_before_checking_activation(self):
        session = SimpleNamespace()

        with (
            patch(
                "db.dal.user_dal.lock_user_by_id",
                AsyncMock(return_value=None),
            ) as lock_user,
            patch.object(
                promo_code_dal,
                "get_user_activation_for_promo",
                AsyncMock(),
            ) as get_activation,
        ):
            activation = await promo_code_dal.consume_promo_activation(
                session,
                promo_code_id=5,
                user_id=42,
            )

        self.assertIsNone(activation)
        lock_user.assert_awaited_once_with(session, 42)
        get_activation.assert_not_awaited()

    async def test_lock_user_by_id_uses_row_lock(self):
        user = SimpleNamespace(user_id=42)
        session = SimpleNamespace(execute=AsyncMock(return_value=_ScalarResult(user)))

        result = await user_dal.lock_user_by_id(session, 42)

        self.assertIs(result, user)
        stmt = session.execute.await_args.args[0]
        sql = str(
            stmt.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).upper()
        self.assertIn("USERS.USER_ID = 42", sql)
        self.assertIn("FOR UPDATE", sql)
