from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import promo_code_dal


def test_picker_query_filters_redeemable_shared_codes_and_escapes_search_wildcards():
    scalar_result = SimpleNamespace(all=list)
    execute = AsyncMock(return_value=SimpleNamespace(scalars=lambda: scalar_result))
    session = cast(
        AsyncSession,
        SimpleNamespace(execute=execute),
    )

    asyncio.run(
        promo_code_dal.get_usable_promo_codes_for_picker(
            session,
            search="SAVE_10%",
            personal=False,
            limit=500,
        )
    )

    statement = execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    values = set(compiled.params.values())

    assert "promo_codes.is_active IS true" in sql
    assert "promo_codes.user_id IS NULL" in sql
    assert "coalesce(promo_codes.current_activations" in sql
    assert "promo_codes.valid_until IS NULL" in sql
    assert "%save\\_10\\%%" in values
    assert "save\\_10\\%%" in values
    assert "save_10%" in values
    assert 100 in values


def test_management_query_applies_search_status_and_scope_filters():
    scalar_result = SimpleNamespace(all=list)
    execute = AsyncMock(return_value=SimpleNamespace(scalars=lambda: scalar_result))
    session = cast(AsyncSession, SimpleNamespace(execute=execute))

    asyncio.run(
        promo_code_dal.get_all_promo_codes_with_details(
            session,
            search="SAVE_10%",
            status="active",
            scope="subscription",
        )
    )

    statement = execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    values = set(compiled.params.values())

    assert "lower(promo_codes.code) LIKE" in sql
    assert "promo_codes.is_active IS true" in sql
    assert "promo_codes.valid_until IS NULL" in sql
    assert "coalesce(promo_codes.current_activations" in sql
    assert "lower(promo_codes.applies_to)" in sql
    assert "%save\\_10\\%%" in values
    assert "subscription" in values


def test_revenue_summary_counts_all_links_and_groups_successful_external_payments():
    execute = AsyncMock(
        side_effect=[
            SimpleNamespace(scalar_one=lambda: 3),
            SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(currency="RUB", amount=160.0, payments=2),
                    SimpleNamespace(currency="USD", amount=10.0, payments=1),
                ]
            ),
        ]
    )
    session = cast(AsyncSession, SimpleNamespace(execute=execute))

    summary = asyncio.run(promo_code_dal.get_promo_revenue_summary(session, 5))

    assert summary == promo_code_dal.PromoRevenueSummary(
        payments_total=3,
        revenue_payments=3,
        currencies=[
            promo_code_dal.PromoRevenueCurrency(currency="RUB", amount=160.0, payments=2),
            promo_code_dal.PromoRevenueCurrency(currency="USD", amount=10.0, payments=1),
        ],
    )
    revenue_statement = execute.await_args_list[1].args[0]
    sql = str(revenue_statement.compile(dialect=postgresql.dialect()))
    assert "payments.status =" in sql
    assert "payments.funding_source =" in sql
    assert "GROUP BY" in sql
