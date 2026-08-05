from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.handlers.admin.sync_admin_runner import perform_sync
from bot.middlewares.i18n import JsonI18n
from bot.services.panel_api_service import PanelApiService
from config.settings import Settings
from db.models import Subscription, User
from tests.support.settings_stub import settings_stub

REPO_ROOT = Path(__file__).resolve().parents[2]
SEEDED_TELEGRAM_IDS = (910000001, 910000002, 910000003)
pytestmark = pytest.mark.skipif(
    os.getenv("QA_REMNAWAVE_UPGRADE") != "1",
    reason="requires the scheduled same-database Remnawave upgrade stand",
)


def _read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result


def _async_dsn() -> str:
    dsn = os.getenv(
        "QA_DB_DSN",
        "postgresql://remnawave_minishop:remnawave_minishop@127.0.0.1:6768/remnawave_minishop",
    )
    return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)


async def _verify_upgrade() -> None:
    env = _read_env(REPO_ROOT / ".env.remnawave-dev")
    settings = cast(
        Settings,
        settings_stub(
            PANEL_API_URL=os.getenv("QA_REMNAWAVE_API_URL", "http://127.0.0.1:3000/api"),
            PANEL_API_KEY=os.getenv("QA_REMNAWAVE_API_TOKEN") or env["REMNAWAVE_DEV_API_TOKEN"],
            PANEL_WRITE_MODE="live",
            PANEL_ALL_USERS_CACHE_TTL_SECONDS=0,
            PANEL_USER_CACHE_TTL_SECONDS=0,
            PANEL_DEVICES_CACHE_TTL_SECONDS=0,
            REDIS_URL=None,
            DATABASE_URL=_async_dsn(),
        ),
    )
    service = PanelApiService(settings)
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    i18n = JsonI18n(str(REPO_ROOT / "locales"), default="en")
    try:
        compatibility = await service.get_panel_api_compatibility(force_refresh=True)
        assert compatibility.version is not None
        assert compatibility.version.lstrip("v") == "3.2.1"

        async with sessions() as session:
            seeded_user_ids = list(
                (
                    await session.scalars(
                        select(User.user_id).where(User.telegram_id.in_(SEEDED_TELEGRAM_IDS))
                    )
                ).all()
            )
            subscriptions_before = int(
                await session.scalar(
                    select(func.count(Subscription.subscription_id)).where(
                        Subscription.user_id.in_(seeded_user_ids)
                    )
                )
                or 0
            )
            assert subscriptions_before > 0

        async with sessions() as session:
            result = await perform_sync(service, session, settings, i18n)
            assert result["status"] == "completed", result
            assert result["errors"] == [], result

        async with sessions() as session:
            users = list(
                (
                    await session.scalars(
                        select(User).where(User.telegram_id.in_(SEEDED_TELEGRAM_IDS))
                    )
                ).all()
            )
            assert {user.telegram_id for user in users} == set(SEEDED_TELEGRAM_IDS)
            assert all(str(user.panel_user_uuid or "").isdecimal() for user in users)

            subscriptions = list(
                (
                    await session.scalars(
                        select(Subscription).where(
                            Subscription.user_id.in_([user.user_id for user in users])
                        )
                    )
                ).all()
            )
            assert len(subscriptions) == subscriptions_before
            subscription_refs = [
                str(subscription.panel_subscription_uuid or "") for subscription in subscriptions
            ]
            assert all(subscription_refs)
            assert len(set(subscription_refs)) == len(subscription_refs)
            assert all(subscription.panel_user_uuid.isdecimal() for subscription in subscriptions)
            active_subscriptions = [
                subscription for subscription in subscriptions if subscription.is_active
            ]
            assert active_subscriptions
    finally:
        await service.close_session()
        await engine.dispose()


def test_same_database_2_8_1_to_3_2_1_upgrade_and_sync() -> None:
    assert os.getenv("QA_REMNAWAVE_UPGRADE_FROM") == "2.8.1"
    assert os.getenv("QA_REMNAWAVE_PRESET") == "3.2.1"
    asyncio.run(_verify_upgrade())
