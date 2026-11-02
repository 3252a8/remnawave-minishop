"""First-owner identity checks and concurrent sign-ins on disposable PostgreSQL."""

import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.services.account_roles import bootstrap_configured_owner, bootstrap_owner
from db.auth_models import AccountAlias, AccountRole, AccountRoleEvent, UserEmailAddress
from db.dal.user_delete_dal import delete_user_and_relations
from db.models import Base, User

DATABASE_URL = os.environ.get("CORE_PERFORMANCE_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="Disposable PostgreSQL URL is required")


def run_scenario(scenario: Callable[[Any], Awaitable[None]]) -> None:
    async def run() -> None:
        schema = "owner_bootstrap_test_" + uuid.uuid4().hex
        admin = create_async_engine(DATABASE_URL)
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            DATABASE_URL, connect_args={"server_settings": {"search_path": schema}}
        )
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
            async with factory() as session:
                session.add_all(
                    [
                        User(user_id=1, telegram_id=777),
                        User(user_id=777, email="pending@example.com"),
                        User(
                            user_id=2,
                            email="Owner@example.com",
                            email_verified_at=datetime.now(UTC),
                        ),
                        User(user_id=3, telegram_id=888, is_banned=True),
                        User(user_id=4, account_id=uuid.UUID("4" * 32)),
                    ]
                )
                await session.flush()
                session.add(
                    UserEmailAddress(
                        user_id=1,
                        email="secondary@example.com",
                        verified_at=datetime.now(UTC),
                        source="email",
                    )
                )
                await session.commit()
            await scenario(factory)
        finally:
            await engine.dispose()
            async with admin.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin.dispose()

    asyncio.run(run())


@pytest.mark.parametrize(
    "user_id,identities,expected",
    [
        (1, {"telegram_id": 777}, True),
        (777, {"telegram_id": 777}, False),
        (2, {"email": " OWNER@EXAMPLE.COM "}, True),
        (777, {"email": "pending@example.com"}, False),
        (1, {"email": "secondary@example.com"}, True),
        (2, {"telegram_id": 777, "email": "owner@example.com"}, True),
        (1, {"email": "owner@example.com"}, False),
        (3, {"telegram_id": 888}, False),
        (999, {"telegram_id": 777}, False),
        (1, {}, False),
    ],
)
def test_configured_owner_requires_matching_verified_account(
    user_id: int, identities: dict[str, Any], expected: bool
) -> None:
    async def scenario(factory: Any) -> None:
        async with factory() as session:
            assert await bootstrap_configured_owner(session, user_id, **identities) is expected
            await session.commit()
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(AccountRole)) == int(
                expected
            )
            assert await session.scalar(select(func.count()).select_from(AccountRoleEvent)) == int(
                expected
            )

    run_scenario(scenario)


def test_simultaneous_matching_accounts_receive_only_one_owner_and_do_not_regain_it() -> None:
    async def scenario(factory: Any) -> None:
        async def sign_in(user_id: int) -> bool:
            async with factory() as session:
                granted = await bootstrap_configured_owner(
                    session, user_id, telegram_id=777, email="owner@example.com"
                )
                await session.commit()
                return bool(granted)

        assert sum(await asyncio.gather(sign_in(1), sign_in(2))) == 1
        async with factory() as session:
            owner = await session.scalar(select(AccountRole.user_id))
            assert owner in (1, 2)
            assert await session.scalar(select(func.count()).select_from(AccountRoleEvent)) == 1
            with pytest.raises(ValueError, match="Owner already exists"):
                await bootstrap_owner(session, minishop_id="ms_missing")
            # Retained history must also protect against stale configuration
            # after an assignment has been revoked outside the normal last-owner guard.
            await session.execute(update(AccountRole).values(revoked_at=datetime.now(UTC)))
            await session.commit()
        assert not await sign_in(1)
        assert not await sign_in(2)

    run_scenario(scenario)


@pytest.mark.parametrize(
    "identifier,expected",
    [
        ({"telegram_id": 777}, 1),
        ({"email": "SECONDARY@example.com"}, 1),
        ({"email": "pending@example.com"}, None),
        ({"telegram_id": 888}, None),
        ({"minishop_id": "ms_" + "4" * 32}, 4),
    ],
)
def test_manual_owner_command_resolves_verified_identities(
    identifier: dict[str, Any], expected: int | None
) -> None:
    async def scenario(factory: Any) -> None:
        async with factory() as session:
            if expected is None:
                with pytest.raises(ValueError):
                    await bootstrap_owner(session, **identifier)
                return
            assert await bootstrap_owner(session, **identifier) == expected
            await session.commit()

    run_scenario(scenario)


def test_manually_assigned_owner_prevents_configured_accounts_from_becoming_owners() -> None:
    async def scenario(factory: Any) -> None:
        async with factory() as session:
            assert await bootstrap_owner(session, minishop_id="ms_" + "4" * 32) == 4
            await session.commit()
        for user_id in (1, 2):
            async with factory() as session:
                assert not await bootstrap_configured_owner(
                    session, user_id, telegram_id=777, email="owner@example.com"
                )
        async with factory() as session:
            assert (await session.execute(select(AccountRole.user_id))).scalars().all() == [4]

    run_scenario(scenario)


@pytest.mark.parametrize("revoked", [False, True])
def test_delete_account_cleans_roles_aliases_and_retains_other_accounts_history(
    revoked: bool,
) -> None:
    async def scenario(factory: Any) -> None:
        async with factory() as session:
            session.add_all(
                [
                    AccountRole(
                        user_id=1,
                        role="admin",
                        granted_by=2,
                        revoked_at=datetime.now(UTC) if revoked else None,
                    ),
                    AccountRole(user_id=2, role="admin", granted_by=1, revoked_by=1),
                    AccountRoleEvent(
                        user_id=1, role="admin", action="grant", actor_user_id=2, source="manual"
                    ),
                    AccountRoleEvent(
                        user_id=2, role="admin", action="grant", actor_user_id=1, source="manual"
                    ),
                    AccountAlias(old_user_id=99, new_user_id=1, reason="telegram_link"),
                    AccountAlias(old_user_id=100, new_user_id=2, reason="telegram_link"),
                ]
            )
            await session.commit()
        async with factory() as session:
            assert await delete_user_and_relations(session, 1)
            await session.commit()
        async with factory() as session:
            assert await session.get(User, 1) is None
            assert await session.get(User, 2) is not None
            roles = (await session.execute(select(AccountRole))).scalars().all()
            assert len(roles) == 1
            assert roles[0].user_id == 2
            assert roles[0].granted_by is None
            assert roles[0].revoked_by is None
            events = (await session.execute(select(AccountRoleEvent))).scalars().all()
            assert len(events) == 1
            assert events[0].user_id == 2
            assert events[0].actor_user_id is None
            assert events[0].action == "grant"
            aliases = (await session.execute(select(AccountAlias))).scalars().all()
            assert [(alias.old_user_id, alias.new_user_id) for alias in aliases] == [(100, 2)]
            assert not await delete_user_and_relations(session, 1)

    run_scenario(scenario)
