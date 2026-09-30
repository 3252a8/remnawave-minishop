import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.services import subscription_reissue_access as access_service
from db.subscription_access_rotation_models import SubscriptionAccessRotation
from tests.support.settings_stub import settings_stub


class SubscriptionReissueAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_database_rotation_coalesces_concurrency_and_recovers_timeout(self):
        import asyncio

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from db.base import Base
        from db.models import Subscription, User

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                session.add(User(user_id=42, panel_user_uuid="panel-user"))
                sub = Subscription(
                    user_id=42,
                    panel_user_uuid="panel-user",
                    panel_subscription_uuid="old-short",
                    end_date=datetime.now(UTC) + timedelta(days=30),
                    is_active=True,
                )
                session.add(sub)
                await session.flush()
                old_token = await access_service.subscription_dal.ensure_install_share_token(
                    session, sub, panel_short_uuid="old-short"
                )
                await session.commit()
            started = asyncio.Event()
            release = asyncio.Event()
            panel_user = {
                "shortUuid": "old-short",
                "subscriptionUrl": "https://panel.test/old-short",
            }
            calls = 0

            async def revoke(_uuid):
                nonlocal calls
                calls += 1
                started.set()
                await release.wait()
                panel_user.update(
                    shortUuid="new-short", subscriptionUrl="https://panel.test/new-short"
                )
                raise TimeoutError("Response lost after rotation")

            panel = SimpleNamespace(
                get_user_by_uuid=AsyncMock(side_effect=lambda *_args, **_kwargs: dict(panel_user)),
                revoke_user_subscription=revoke,
            )
            settings = settings_stub(
                SUBSCRIPTION_GATEWAY_ENABLED=True,
                SUBSCRIPTION_LINK_MODE="minishop",
                SUBSCRIPTION_MINI_APP_URL="https://shop.test/",
            )

            async def rotate():
                async with factory() as session:
                    return await access_service.reissue_subscription_access(
                        session, panel, user_id=42, panel_user_uuid="panel-user", settings=settings
                    )

            first = asyncio.create_task(rotate())
            await asyncio.wait_for(started.wait(), timeout=5)
            async with factory() as session:
                self.assertIsNone(
                    await access_service.subscription_dal.get_subscription_by_install_share_token(
                        session, old_token
                    )
                )
            with self.assertRaises(access_service.AccessRotationBusy):
                await rotate()
            release.set()
            self.assertEqual(await first, (None, None))
            recovered = await rotate()
            coalesced = await rotate()
            self.assertEqual(calls, 1)
            self.assertEqual(recovered, coalesced)
            self.assertEqual(recovered[0]["shortUuid"], "new-short")
            self.assertTrue(recovered[1].startswith("https://shop.test/s/"))
            async with factory() as session:
                self.assertIsNone(
                    await access_service.subscription_dal.get_subscription_by_install_share_token(
                        session, old_token
                    )
                )
        finally:
            await engine.dispose()

    async def test_reissue_commits_old_revocation_before_panel_and_binds_new_link(self) -> None:
        events: list[str] = []

        async def commit() -> None:
            events.append("commit")

        async def revoke(_session: object, _panel_uuid: str) -> None:
            events.append("revoke")

        async def panel_revoke(_panel_uuid: str) -> dict[str, str]:
            events.append("panel")
            assert events[:2] == ["revoke", "commit"]
            return {"shortUuid": "new-short", "subscriptionUrl": "https://panel.test/new-short"}

        subscription = SimpleNamespace(panel_subscription_uuid="old-short")
        updated = {"shortUuid": "new-short", "subscriptionUrl": "https://panel.test/new-short"}
        panel = SimpleNamespace(
            revoke_user_subscription=panel_revoke,
            get_user_by_uuid=AsyncMock(side_effect=[{"shortUuid": "old-short"}, updated]),
        )
        session = SimpleNamespace(commit=commit)
        rotation = SubscriptionAccessRotation(
            state="pending",
            old_short_uuid="old-short",
            lease_until=datetime.now(UTC) - timedelta(seconds=1),
        )
        with (
            patch.object(access_service.user_dal, "lock_user_by_id", AsyncMock()),
            patch.object(access_service, "_rotation", AsyncMock(return_value=rotation)),
            patch.object(
                access_service.subscription_dal,
                "revoke_install_share_tokens_for_panel_user",
                side_effect=revoke,
            ),
            patch.object(
                access_service.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=subscription),
            ),
            patch.object(
                access_service.subscription_dal,
                "ensure_install_share_token",
                AsyncMock(return_value="a" * 32),
            ),
        ):
            updated, url = await access_service.reissue_subscription_access(
                session,
                panel,
                user_id=42,
                panel_user_uuid="panel-user",
                settings=settings_stub(
                    SUBSCRIPTION_GATEWAY_ENABLED=True,
                    SUBSCRIPTION_LINK_MODE="minishop",
                    SUBSCRIPTION_MINI_APP_URL="https://shop.test/",
                ),
            )
        assert updated and updated["shortUuid"] == "new-short"
        assert subscription.panel_subscription_uuid == "new-short"
        assert url == f"https://shop.test/s/{'a' * 32}"
        assert events == ["revoke", "commit", "panel", "revoke", "commit"]

    async def test_pending_rotation_blocks_concurrent_request(self):
        rotation = SubscriptionAccessRotation(
            state="pending", lease_until=datetime.now(UTC) + timedelta(seconds=90)
        )
        panel = AsyncMock()
        with (
            patch.object(access_service.user_dal, "lock_user_by_id", AsyncMock()),
            patch.object(
                access_service.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=object()),
            ),
            patch.object(access_service, "_rotation", AsyncMock(return_value=rotation)),
            self.assertRaises(access_service.AccessRotationBusy),
        ):
            await access_service.reissue_subscription_access(
                AsyncMock(),
                panel,
                user_id=42,
                panel_user_uuid="panel-user",
                settings=settings_stub(),
            )
        panel.revoke_user_subscription.assert_not_awaited()

    async def test_ambiguous_rotation_recovers_without_another_panel_revoke(self):
        rotation = SubscriptionAccessRotation(
            state="pending",
            old_short_uuid="old-short",
            lease_until=datetime.now(UTC) - timedelta(seconds=1),
        )
        panel = SimpleNamespace(
            get_user_by_uuid=AsyncMock(return_value={"shortUuid": "new-short"}),
            revoke_user_subscription=AsyncMock(),
        )
        session = AsyncMock()
        with (
            patch.object(access_service.user_dal, "lock_user_by_id", AsyncMock()),
            patch.object(
                access_service.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=SimpleNamespace(panel_subscription_uuid="old-short")),
            ),
            patch.object(
                access_service.subscription_dal,
                "revoke_install_share_tokens_for_panel_user",
                AsyncMock(),
            ),
            patch.object(
                access_service.subscription_dal,
                "ensure_install_share_token",
                AsyncMock(return_value="a" * 32),
            ),
            patch.object(access_service, "_rotation", AsyncMock(return_value=rotation)),
        ):
            result, _url = await access_service.reissue_subscription_access(
                session, panel, user_id=42, panel_user_uuid="panel-user", settings=settings_stub()
            )
            self.assertEqual(result["shortUuid"], "new-short")
            self.assertEqual(rotation.state, "completed")
            # The same result is coalesced for requests that just completed.
            await access_service.reissue_subscription_access(
                session, panel, user_id=42, panel_user_uuid="panel-user", settings=settings_stub()
            )
        panel.revoke_user_subscription.assert_not_awaited()
