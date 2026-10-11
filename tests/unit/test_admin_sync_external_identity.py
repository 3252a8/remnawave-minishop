"""Native identity replacement preserves real unique keys and subscription references."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.app.web.webapp import subscription_access
from bot.handlers.admin.sync_admin_duplicates import _absorb_duplicate_panel_identity
from config.tariffs_config import TariffsConfig
from db.base import Base
from db.dal import subscription_dal
from db.models import (
    HwidDevicePurchase,
    Subscription,
    SubscriptionNotification,
    User,
    UserPanelSquadOverride,
)


@pytest.mark.parametrize("source_imported", [False, True])
@pytest.mark.parametrize("failed_step", [None, "update", "delete"])
def test_external_panel_replacement_preserves_sql_entitlements(
    tmp_path, source_imported, failed_step
):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'merge.sqlite'}")
        try:
            async with engine.begin() as connection:
                await connection.execute(text("PRAGMA foreign_keys=ON"))
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                now = datetime.now(UTC)
                owner = User(user_id=42, telegram_id=123456789, panel_user_uuid="generated")
                target = Subscription(
                    subscription_id=10,
                    user_id=42,
                    panel_user_uuid="generated",
                    panel_subscription_uuid="generated-link",
                    end_date=now + timedelta(days=10),
                    is_active=True,
                    status_from_panel="ACTIVE",
                    tariff_key="saved-plan",
                    auto_renew_enabled=True,
                    auto_renew_consent_version=8,
                    topup_balance_bytes=12345,
                    hwid_device_limit=6,
                    extra_hwid_devices=100,
                    traffic_limit_bytes=9876,
                    install_share_token="a" * 32,
                    install_share_panel_short_uuid="generated-link",
                )
                history = Subscription(
                    subscription_id=9,
                    user_id=42,
                    panel_user_uuid="generated",
                    panel_subscription_uuid="historical-link",
                    end_date=now - timedelta(days=60),
                    is_active=False,
                )
                source = Subscription(
                    subscription_id=11,
                    user_id=42,
                    panel_user_uuid="external",
                    panel_subscription_uuid="external-link",
                    end_date=now + timedelta(days=30),
                    is_active=True,
                    status_from_panel="ACTIVE",
                )
                override = UserPanelSquadOverride(
                    user_id=42,
                    panel_user_uuid="generated",
                    kind="internal",
                    override_key="paid-access",
                    squad_uuid="saved-squad",
                    source="admin",
                )
                session.add_all([owner, target, history, override])
                if source_imported:
                    session.add(source)
                await session.flush()
                session.add_all(
                    [
                        HwidDevicePurchase(
                            subscription_id=10,
                            purchased_devices=7,
                            valid_until=now - timedelta(days=1),
                        ),
                        HwidDevicePurchase(
                            subscription_id=10,
                            purchased_devices=4,
                            valid_from=now + timedelta(days=1),
                        ),
                        HwidDevicePurchase(
                            subscription_id=10,
                            purchased_devices=2,
                            valid_from=now - timedelta(days=1),
                            valid_until=now + timedelta(days=2),
                        ),
                    ]
                )
                notification = SubscriptionNotification(
                    subscription_id=10, notification_key="before_1d:telegram"
                )
                session.add(notification)
                await session.commit()
                generated = {
                    "uuid": "generated",
                    "shortUuid": "generated-link",
                    "username": owner.minishop_id,
                    "telegramId": 123456789,
                    "status": "ACTIVE",
                    "expireAt": (now + timedelta(days=10)).isoformat(),
                    "trafficLimitBytes": 9876,
                    "hwidDeviceLimit": 6,
                    "activeInternalSquads": [{"uuid": "saved-squad", "name": "Saved"}],
                }
                external = {
                    "uuid": "external",
                    "shortUuid": "external-link",
                    "username": "original_manual_name",
                    "telegramId": 123456789,
                    "status": "ACTIVE",
                    "expireAt": (now + timedelta(days=30)).isoformat(),
                    "trafficLimitBytes": 123,
                    "hwidDeviceLimit": 1,
                }
                # The prefetched indexes can miss a payment/import committed before
                # the user lock. Fresh SQL reads must preserve those current rows.
                subscriptions = {}
                panel = SimpleNamespace(
                    update_user_details_on_panel=AsyncMock(
                        return_value=None if failed_step == "update" else {"uuid": "external"}
                    ),
                    delete_user_from_panel=AsyncMock(return_value=failed_step != "delete"),
                )

                async def assert_durable_before_patch(*args, **kwargs):
                    async with factory() as observer:
                        saved_owner = await observer.get(User, 42)
                        saved_target = await observer.get(Subscription, 10)
                        assert saved_owner.panel_user_uuid == "external"
                        assert saved_target.panel_subscription_uuid == "external-link"
                        receipt = await observer.scalar(
                            select(Subscription).where(
                                Subscription.panel_subscription_uuid == "generated-link"
                            )
                        )
                        assert receipt.status_from_panel == "MERGED_PANEL_REPLACED"
                        assert not receipt.is_active
                    return None if failed_step == "update" else {"uuid": "external"}

                panel.update_user_details_on_panel.side_effect = assert_durable_before_patch
                kwargs = {
                    "panel_service": panel,
                    "existing_user": owner,
                    "keep_panel_uuid": "generated",
                    "keep_panel_user": generated,
                    "duplicate_panel_user": external,
                    "settings": SimpleNamespace(
                        user_traffic_limit_bytes=0,
                        tariffs_config=None,
                        USER_TRAFFIC_STRATEGY="MONTH",
                        TRIAL_TRAFFIC_STRATEGY="NO_RESET",
                    ),
                    "subscriptions_by_panel_uuid": subscriptions,
                    "active_subscriptions_by_user_panel": {(42, "generated"): target},
                    "preserve_duplicate_identity": True,
                }
                with patch(
                    "db.advisory_locks.acquire_subscription_background_sync_lock", AsyncMock()
                ):
                    first = await _absorb_duplicate_panel_identity(session, **kwargs)
                    assert first["resolved"] == (failed_step is None)
                    final_end = target.end_date
                    if failed_step:
                        if failed_step == "update":
                            panel.delete_user_from_panel.assert_not_awaited()
                        kwargs.update(
                            {
                                "keep_panel_uuid": "external",
                                "keep_panel_user": external,
                                "duplicate_panel_user": generated,
                                "preserve_duplicate_identity": False,
                            }
                        )
                        # The panel's old expiry cannot erase the committed transfer receipt.
                        target.end_date = now + timedelta(days=10)
                        if failed_step == "delete":
                            target.tariff_key = "renewed-plan"
                            target.traffic_limit_bytes = 22222
                            target.hwid_device_limit = 8
                            target.extra_hwid_devices = 2
                            target.tariff_managed_squad_uuids = '["new-paid-squad"]'
                            kwargs["settings"].tariffs_config = TariffsConfig.model_validate(
                                {
                                    "default_tariff": "renewed-plan",
                                    "tariffs": [
                                        {
                                            "key": "renewed-plan",
                                            "billing_model": "period",
                                            "monthly_gb": 100,
                                            "prices_rub": {"1": 100},
                                            "enabled_periods": [1],
                                            "squad_uuids": ["new-paid-squad"],
                                            "traffic_limit_strategy": "DAY",
                                            "premium_squad_uuids": ["premium-squad"],
                                        }
                                    ],
                                }
                            )
                            target.premium_is_limited = True
                        override.is_active = False
                        session.add_all(
                            [
                                UserPanelSquadOverride(
                                    user_id=42,
                                    panel_user_uuid="external",
                                    kind="internal",
                                    override_key="new-manual",
                                    squad_uuid="new-manual",
                                    source="admin",
                                ),
                                UserPanelSquadOverride(
                                    user_id=42,
                                    panel_user_uuid="external",
                                    kind="external",
                                    override_key="external",
                                    mode="cleared",
                                    source="admin",
                                ),
                            ]
                        )
                        await session.commit()
                        panel.update_user_details_on_panel.side_effect = None
                        panel.update_user_details_on_panel.return_value = {"uuid": "external"}
                        panel.delete_user_from_panel.return_value = True
                        assert (await _absorb_duplicate_panel_identity(session, **kwargs))[
                            "resolved"
                        ]
                    await session.commit()
                await session.refresh(target)
                await session.refresh(history)
                await session.refresh(override)
                assert target.subscription_id == notification.subscription_id == 10
                assert target.panel_user_uuid == history.panel_user_uuid == "external"
                assert target.panel_subscription_uuid == "external-link"
                assert target.tariff_key == (
                    "renewed-plan" if failed_step == "delete" else "saved-plan"
                )
                assert target.topup_balance_bytes == 12345
                assert target.auto_renew_enabled and target.auto_renew_consent_version == 8
                assert target.hwid_device_limit == (8 if failed_step == "delete" else 6)
                assert target.install_share_token == "a" * 32
                assert target.install_share_panel_short_uuid == "external-link"
                assert (
                    await subscription_dal.ensure_install_share_token(
                        session, target, panel_short_uuid="external-link"
                    )
                    == "a" * 32
                )
                lookup = SimpleNamespace(
                    get_user_by_uuid_lookup=AsyncMock(
                        return_value={
                            "ok": True,
                            "user": {
                                **external,
                                "subscriptionUrl": "https://panel.test/sub/external-link",
                            },
                        }
                    )
                )
                with (
                    patch.object(subscription_access, "get_session_factory", return_value=factory),
                    patch.object(
                        subscription_access, "_panel_service_from_app", return_value=lookup
                    ),
                ):
                    access = await subscription_access.resolve_subscription_access(
                        make_mocked_request("GET", "/s/" + "a" * 32, app=web.Application()),
                        "a" * 32,
                    )
                assert access is not None
                assert (
                    access.panel_user_uuid == "external"
                    and access.panel_short_uuid == "external-link"
                )
                assert target.end_date == final_end
                assert now.replace(tzinfo=None) + timedelta(days=39) < final_end
                assert override.panel_user_uuid == "external"
                assert override.squad_uuid == "saved-squad" and override.is_active == (
                    failed_step is None
                )
                assert owner.panel_username == external["username"] == "original_manual_name"
                payload = panel.update_user_details_on_panel.await_args.args[1]
                assert panel.update_user_details_on_panel.await_args.args[0] == "external"
                assert payload["trafficLimitBytes"] == (22222 if failed_step == "delete" else 9876)
                assert payload["hwidDeviceLimit"] == (10 if failed_step == "delete" else 8)
                if failed_step == "delete":
                    assert payload["trafficLimitStrategy"] == "DAY"
                    assert payload["activeInternalSquads"] == ["new-paid-squad", "new-manual"]
                if failed_step == "update":
                    assert payload["activeInternalSquads"] == ["new-manual"]
                if failed_step:
                    assert payload["externalSquadUuid"] is None
                assert not {"username", "uuid", "shortUuid", "subscriptionUuid"} & payload.keys()
                panel.delete_user_from_panel.assert_awaited_with("generated", log_response=False)
        finally:
            await engine.dispose()

    asyncio.run(run())
