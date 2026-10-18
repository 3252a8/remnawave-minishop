"""Bulk sync repairs synthetic panel migrations without replacing paid records."""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.handlers.admin.sync_admin_runner import perform_sync
from bot.middlewares.i18n import JsonI18n
from bot.services.panel_identity_match import panel_origin_fingerprint
from db.models import Base, PanelSyncStatus, Subscription, User, UserPanelSquadOverride
from tests.support.settings_stub import settings_stub

DATABASE_URL = os.environ.get("CORE_PERFORMANCE_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="Disposable PostgreSQL URL is required")


@pytest.mark.parametrize("identity", ["telegram", "email", "username"])
@pytest.mark.parametrize("purchase_during_fetch", [False, True])
def test_bulk_sync_relinks_history_and_preserves_paid_state(identity, purchase_during_fetch):
    async def run():
        schema = "sync_relink_" + uuid.uuid4().hex
        admin = create_async_engine(DATABASE_URL)
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            DATABASE_URL, connect_args={"server_settings": {"search_path": schema}}
        )
        try:
            async with engine.begin() as connection:
                await connection.run_sync(
                    lambda connection: Base.metadata.create_all(
                        connection,
                        tables=[
                            User.__table__,
                            Subscription.__table__,
                            UserPanelSquadOverride.__table__,
                            PanelSyncStatus.__table__,
                        ],
                    )
                )
            factory = async_sessionmaker(engine, expire_on_commit=False)
            now = datetime.now(UTC)
            end = now + timedelta(days=20)
            old_reference = "10000000-0000-4000-8000-000000000001"
            settings = settings_stub()
            telegram_id = 910000071 if identity == "telegram" else None
            email = "synthetic-owner@example.test" if identity == "email" else None
            panel_user = {
                "uuid": "701",
                "shortUuid": "kept-public-token",
                "username": "synthetic_legacy" if identity == "username" else "renamed_profile",
                "telegramId": telegram_id,
                "email": email,
                "description": "",
                "status": "ACTIVE",
                "expireAt": end.isoformat(),
            }
            second_panel_user = {
                **panel_user,
                "uuid": "702",
                "shortUuid": "second-public-token",
                "username": "second_profile",
                "telegramId": 910000072,
                "email": None,
            }
            async with factory() as session:
                user = User(
                    user_id=71,
                    panel_user_uuid=old_reference,
                    panel_username="synthetic_legacy",
                    panel_origin=panel_origin_fingerprint(settings.PANEL_API_URL),
                    telegram_id=telegram_id,
                    email=email,
                    email_verified_at=now if email else None,
                )
                current = Subscription(
                    subscription_id=81,
                    user_id=71,
                    panel_user_uuid=old_reference,
                    panel_subscription_uuid="kept-public-token",
                    end_date=end,
                    is_active=True,
                    status_from_panel="ACTIVE",
                    tariff_key="saved-plan",
                    auto_renew_enabled=True,
                    auto_renew_consent_version=9,
                    topup_balance_bytes=4096,
                    install_share_token="b" * 32,
                    install_share_panel_short_uuid="kept-public-token",
                )
                history = Subscription(
                    subscription_id=80,
                    user_id=71,
                    panel_user_uuid=old_reference,
                    panel_subscription_uuid="older-public-token",
                    end_date=now - timedelta(days=30),
                    is_active=False,
                )
                override = UserPanelSquadOverride(
                    user_id=71,
                    panel_user_uuid=old_reference,
                    kind="internal",
                    override_key="paid-access",
                    squad_uuid="synthetic-squad",
                    source="admin",
                )
                second_user = User(
                    user_id=72,
                    panel_user_uuid="10000000-0000-4000-8000-000000000002",
                    panel_username="second_profile",
                    panel_origin=user.panel_origin,
                    telegram_id=910000072,
                )
                second_sub = Subscription(
                    subscription_id=82,
                    user_id=72,
                    panel_user_uuid=second_user.panel_user_uuid,
                    panel_subscription_uuid="second-public-token",
                    end_date=end,
                    is_active=True,
                    status_from_panel="ACTIVE",
                )
                session.add_all([user, current, history, override, second_user, second_sub])
                await session.commit()

            async def fetch_panel():
                if purchase_during_fetch:
                    async with factory() as purchase_session:
                        paid = await purchase_session.get(Subscription, 81)
                        paid.end_date = end + timedelta(days=30)
                        paid.tariff_key = "renewed-plan"
                        await purchase_session.commit()
                return [dict(panel_user), dict(second_panel_user)]

            panel = SimpleNamespace(
                get_all_panel_users=AsyncMock(side_effect=fetch_panel),
                update_user_details_on_panel=AsyncMock(),
                get_user_by_uuid=AsyncMock(return_value=panel_user),
            )
            async with factory() as session:
                result = await perform_sync(panel, session, settings, JsonI18n("locales"))
                assert result["status"] == "completed", result["errors"]
                assert result["users_created"] == 0
            async with factory() as session:
                user = await session.get(User, 71)
                current = await session.get(Subscription, 81)
                history = await session.get(Subscription, 80)
                override = await session.scalar(select(UserPanelSquadOverride))
                assert user.panel_user_uuid == current.panel_user_uuid == "701"
                assert history.panel_user_uuid == override.panel_user_uuid == "701"
                assert current.panel_subscription_uuid == "kept-public-token"
                assert history.panel_subscription_uuid == "older-public-token"
                assert history.end_date == now - timedelta(days=30) and not history.is_active
                assert current.end_date == end + timedelta(days=30 if purchase_during_fetch else 0)
                assert current.tariff_key == (
                    "renewed-plan" if purchase_during_fetch else "saved-plan"
                )
                assert current.auto_renew_enabled and current.auto_renew_consent_version == 9
                assert current.topup_balance_bytes == 4096 and current.is_active
                assert current.install_share_token == "b" * 32
                assert current.install_share_panel_short_uuid == "kept-public-token"
                assert override.is_active and override.squad_uuid == "synthetic-squad"
                second_user = await session.get(User, 72)
                second_sub = await session.get(Subscription, 82)
                assert second_user.panel_user_uuid == second_sub.panel_user_uuid == "702"
                panel_user["expireAt"] = current.end_date.isoformat()
                panel.get_all_panel_users.side_effect = None
                panel.get_all_panel_users.return_value = [panel_user, second_panel_user]
                replay = await perform_sync(panel, session, settings, JsonI18n("locales"))
                assert replay["status"] == "completed", replay["errors"]
                assert replay["users_created"] == 0
                assert set((await session.scalars(select(Subscription.subscription_id))).all()) == {
                    80,
                    81,
                    82,
                }
        finally:
            await engine.dispose()
            async with admin.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin.dispose()

    asyncio.run(run())
