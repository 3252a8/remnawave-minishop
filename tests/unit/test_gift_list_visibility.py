from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import gift_dal


async def test_user_gift_list_queries_only_available_gifts() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = []

    await gift_dal.purchased(session, 42)

    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "subscription_gifts.purchaser_id = 42" in sql
    assert "subscription_gifts.status = 'ready'" in sql
    assert "payments.status = 'succeeded'" in sql


async def test_admin_gift_list_keeps_unavailable_gifts_without_status_filter() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = 0
    session.execute.return_value = []

    await gift_dal.admin_list(
        session, status="", query="", page=0, page_size=25, sort="date_desc"
    )

    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "subscription_gifts.status = 'ready'" not in sql
    assert "payments.status = 'succeeded'" not in sql
