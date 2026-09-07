from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import gift_dal


class GiftListVisibilityTests(IsolatedAsyncioTestCase):
    async def test_user_gift_list_queries_only_available_gifts(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        session.execute.return_value = []

        await gift_dal.purchased(session, 42)

        statement = session.execute.await_args.args[0]
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("subscription_gifts.purchaser_id = 42", sql)
        self.assertIn("subscription_gifts.status = 'ready'", sql)
        self.assertIn("payments.status = 'succeeded'", sql)

    async def test_admin_gift_list_keeps_unavailable_gifts_without_status_filter(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        session.scalar.return_value = 0
        session.execute.return_value = []

        await gift_dal.admin_list(
            session,
            status="",
            query="",
            page=0,
            page_size=25,
            sort="date_desc",
        )

        statement = session.execute.await_args.args[0]
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertNotIn("subscription_gifts.status = 'ready'", sql)
        self.assertNotIn("payments.status = 'succeeded'", sql)
