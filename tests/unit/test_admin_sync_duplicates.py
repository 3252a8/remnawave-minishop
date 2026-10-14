import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.handlers.admin.sync_admin_duplicates import (
    _absorb_duplicate_panel_identity,
    _local_replacement_limits,
    _preferred_panel_identity,
)
from bot.handlers.admin.sync_admin_runner import _perform_sync_impl
from bot.middlewares.i18n import JsonI18n
from bot.services.panel_identity_match import panel_origin_fingerprint
from config.tariffs_config import TariffsConfig


@pytest.fixture
def duplicate_case(monkeypatch):
    now = datetime.now(UTC)
    target = SimpleNamespace(
        subscription_id=10,
        user_id=42,
        panel_user_uuid="keep",
        panel_subscription_uuid="sub-keep",
        end_date=now + timedelta(days=10),
        is_active=True,
        status_from_panel="ACTIVE",
    )
    source = SimpleNamespace(
        subscription_id=11,
        user_id=42,
        panel_user_uuid="duplicate",
        panel_subscription_uuid="sub-duplicate",
        end_date=now + timedelta(days=30),
        is_active=True,
        status_from_panel="ACTIVE",
        skip_notifications=False,
    )
    subscriptions = {"sub-keep": target, "sub-duplicate": source}
    stored_rows = [target, source]
    session = SimpleNamespace(
        execute=AsyncMock(), refresh=AsyncMock(), commit=AsyncMock(), flush=AsyncMock()
    )

    async def update_subscription(_session, subscription_id, payload):
        subscription = next(row for row in stored_rows if row.subscription_id == subscription_id)
        for key, value in payload.items():
            setattr(subscription, key, value)
        return subscription

    async def upsert_subscription(_session, payload):
        subscription = SimpleNamespace(subscription_id=20 + len(subscriptions), **payload)
        stored_rows.append(subscription)
        subscriptions[payload["panel_subscription_uuid"]] = subscription
        return subscription

    monkeypatch.setattr(
        "bot.handlers.admin.sync_admin_duplicates.subscription_dal.update_subscription",
        AsyncMock(side_effect=update_subscription),
    )
    monkeypatch.setattr(
        "bot.handlers.admin.sync_admin_duplicates.subscription_dal.upsert_subscription",
        AsyncMock(side_effect=upsert_subscription),
    )
    monkeypatch.setattr(
        "bot.handlers.admin.sync_admin_duplicates.subscription_dal.get_subscription_by_panel_subscription_uuid",
        AsyncMock(side_effect=lambda _session, uuid: subscriptions.get(uuid)),
    )
    monkeypatch.setattr(
        "bot.handlers.admin.sync_admin_duplicates.subscription_dal.get_active_subscription_by_user_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "bot.handlers.admin.sync_admin_duplicates.subscription_panel_identity_dal.relink_panel_subscriptions",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.handlers.admin.sync_admin_duplicates.user_panel_squad_override_dal.merge_panel_user_uuid",
        AsyncMock(),
    )
    panel = SimpleNamespace(
        update_user_details_on_panel=AsyncMock(return_value={"uuid": "keep"}),
        delete_user_from_panel=AsyncMock(return_value=True),
    )
    kwargs = {
        "panel_service": panel,
        "existing_user": SimpleNamespace(
            user_id=42,
            panel_user_uuid="keep",
            telegram_id=123456789,
            email=None,
            username=None,
            first_name=None,
            last_name=None,
            minishop_id="ms_primary",
        ),
        "keep_panel_uuid": "keep",
        "keep_panel_user": {
            "uuid": "keep",
            "username": "ms_primary",
            "shortUuid": "sub-keep",
            "telegramId": 123456789,
            "status": "ACTIVE",
            "expireAt": target.end_date.isoformat(),
        },
        "duplicate_panel_user": {
            "uuid": "duplicate",
            "username": "manually_created",
            "shortUuid": "sub-duplicate",
            "telegramId": 123456789,
            "status": "ACTIVE",
            "expireAt": source.end_date.isoformat(),
        },
        "settings": SimpleNamespace(
            user_traffic_limit_bytes=0,
            tariffs_config=None,
            USER_TRAFFIC_STRATEGY="MONTH",
            TRIAL_TRAFFIC_STRATEGY="NO_RESET",
        ),
        "subscriptions_by_panel_uuid": subscriptions,
        "active_subscriptions_by_user_panel": {},
    }

    def absorb():
        return asyncio.run(_absorb_duplicate_panel_identity(session, **kwargs))

    return SimpleNamespace(
        now=now,
        target=target,
        source=source,
        session=session,
        panel=panel,
        kwargs=kwargs,
        subscriptions=subscriptions,
        absorb=absorb,
    )


@pytest.mark.parametrize("source_imported", [False, True])
@pytest.mark.parametrize("failed_step", ["update", "delete"])
def test_duplicate_retry_does_not_transfer_period_twice(
    duplicate_case, source_imported, failed_step
):
    case = duplicate_case
    if not source_imported:
        case.subscriptions.pop("sub-duplicate")
    initial_end = case.target.end_date
    if failed_step == "update":
        case.panel.update_user_details_on_panel.return_value = None
    else:
        case.panel.delete_user_from_panel.return_value = False

    def assert_receipt_is_committed(*args, **kwargs):
        assert case.session.commit.await_count >= 1
        assert case.subscriptions["sub-duplicate"].status_from_panel == "MERGED_PANEL_DUPLICATE"
        return None if failed_step == "update" else {"uuid": "keep"}

    case.panel.update_user_details_on_panel.side_effect = assert_receipt_is_committed
    first = case.absorb()
    assert not first["resolved"]
    transferred_end = case.target.end_date
    assert case.now + timedelta(days=39) < transferred_end <= case.now + timedelta(days=40)
    if failed_step == "update":
        case.panel.delete_user_from_panel.assert_not_awaited()

    # A fresh synchronization can load the old remote expiry after a failed patch.
    case.target.end_date = initial_end
    case.kwargs["keep_panel_user"]["expireAt"] = initial_end.isoformat()
    case.panel.update_user_details_on_panel.side_effect = None
    case.panel.update_user_details_on_panel.return_value = {"uuid": "keep"}
    case.panel.delete_user_from_panel.return_value = True
    second = case.absorb()

    assert second["resolved"]
    assert case.target.end_date == transferred_end
    assert not case.subscriptions["sub-duplicate"].is_active
    assert case.subscriptions["sub-duplicate"].end_date == transferred_end
    assert case.kwargs["keep_panel_user"]["expireAt"] == (
        transferred_end.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def test_duplicate_transfer_keeps_remote_period_without_local_target(duplicate_case):
    case = duplicate_case
    case.subscriptions.pop("sub-keep")
    assert case.absorb()["resolved"]
    assert case.subscriptions["sub-keep"].end_date > case.now + timedelta(days=39)


def test_duplicate_transfer_preserves_concurrent_purchase(duplicate_case):
    case = duplicate_case

    async def concurrent_purchase():
        case.target.end_date = case.now + timedelta(days=100)

    case.session.commit.side_effect = concurrent_purchase
    assert case.absorb()["resolved"]
    payload = case.panel.update_user_details_on_panel.await_args.args[1]
    assert payload["expireAt"] == (
        case.target.end_date.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def test_disabled_duplicate_does_not_add_days_on_retry(duplicate_case):
    case = duplicate_case
    case.kwargs["duplicate_panel_user"]["status"] = "DISABLED"
    initial_end = case.target.end_date
    case.panel.delete_user_from_panel.return_value = False
    assert not case.absorb()["resolved"]
    case.panel.delete_user_from_panel.return_value = True
    assert case.absorb()["resolved"]
    assert case.target.end_date == initial_end
    case.panel.update_user_details_on_panel.assert_not_awaited()


def test_duplicate_subscription_owned_by_another_local_account_is_preserved(duplicate_case):
    case = duplicate_case
    case.source.user_id = 77
    assert not case.absorb()["resolved"]
    case.panel.update_user_details_on_panel.assert_not_awaited()
    case.panel.delete_user_from_panel.assert_not_awaited()
    case.session.commit.assert_not_awaited()


def test_fresh_other_owner_subscription_is_rejected_when_cached_indexes_miss_it(duplicate_case):
    case = duplicate_case
    case.source.user_id = 77
    fresh = dict(case.subscriptions)
    case.subscriptions.clear()
    with patch(
        "bot.handlers.admin.sync_admin_duplicates.subscription_dal.get_subscription_by_panel_subscription_uuid",
        AsyncMock(side_effect=lambda _session, uuid: fresh.get(uuid)),
    ):
        assert not case.absorb()["resolved"]
    case.panel.update_user_details_on_panel.assert_not_awaited()
    case.panel.delete_user_from_panel.assert_not_awaited()
    case.session.commit.assert_not_awaited()


@pytest.mark.parametrize("failed_step", ["update", "delete"])
@pytest.mark.parametrize("source_imported", [False, True])
def test_external_survivor_retry_preserves_entitlements_once(
    duplicate_case, failed_step, source_imported
):
    case = duplicate_case
    if not source_imported:
        case.subscriptions.pop("sub-duplicate")
    case.target.tariff_key = "paid-plan"
    case.target.topup_balance_bytes = 1234
    case.target.auto_renew_enabled = True
    case.target.auto_renew_consent_version = 8
    case.target.hwid_device_limit = 6
    case.target.traffic_limit_bytes = 777
    case.kwargs["keep_panel_user"].update(
        {
            "trafficLimitBytes": 777,
            "hwidDeviceLimit": 6,
            "activeInternalSquads": ["paid-squad"],
        }
    )
    case.kwargs["preserve_duplicate_identity"] = True
    if failed_step == "update":
        case.panel.update_user_details_on_panel.return_value = None
    else:
        case.panel.delete_user_from_panel.return_value = False
    assert not case.absorb()["resolved"]
    transferred_end = case.target.end_date
    assert case.now + timedelta(days=39) < transferred_end <= case.now + timedelta(days=40)
    assert case.target.subscription_id == 10
    assert case.target.panel_user_uuid == "duplicate"
    assert case.target.panel_subscription_uuid == "sub-duplicate"
    assert case.target.tariff_key == "paid-plan"
    assert case.target.topup_balance_bytes == 1234
    assert case.target.auto_renew_enabled
    assert case.target.auto_renew_consent_version == 8
    assert case.target.hwid_device_limit == 6
    assert case.kwargs["existing_user"].panel_username == "manually_created"
    assert case.subscriptions["sub-keep"].status_from_panel == (
        "MERGED_PANEL_REPLACED" if failed_step == "update" else "MERGED_PANEL_REPLACED_APPLIED"
    )
    if failed_step == "update":
        case.panel.delete_user_from_panel.assert_not_awaited()
    payload = case.panel.update_user_details_on_panel.await_args.args[1]
    assert payload["trafficLimitBytes"] == 777
    assert payload["hwidDeviceLimit"] == 6
    assert payload["activeInternalSquads"] == ["paid-squad"]
    assert not {"username", "uuid", "shortUuid", "subscriptionUuid"} & payload.keys()

    # A later run sees the new local link and the old native record as the duplicate.
    old = case.kwargs["keep_panel_user"]
    case.kwargs.update(
        {
            "keep_panel_uuid": "duplicate",
            "keep_panel_user": case.kwargs["duplicate_panel_user"],
            "duplicate_panel_user": old,
            "preserve_duplicate_identity": False,
        }
    )
    case.target.end_date = case.now + timedelta(days=10)
    case.panel.update_user_details_on_panel.return_value = {"uuid": "duplicate"}
    case.panel.delete_user_from_panel.return_value = True
    assert case.absorb()["resolved"]
    assert case.target.end_date == transferred_end
    assert case.panel.update_user_details_on_panel.await_args.args[0] == "duplicate"
    assert case.panel.update_user_details_on_panel.await_args.args[1]["trafficLimitBytes"] == 777
    case.panel.delete_user_from_panel.assert_awaited_with("keep", log_response=False)
    assert case.kwargs["keep_panel_user"]["username"] == "manually_created"


def test_external_selection_requires_a_unique_unambiguous_survivor(duplicate_case):
    case = duplicate_case
    owner = case.kwargs["existing_user"]
    owned = case.kwargs["keep_panel_user"]
    external = case.kwargs["duplicate_panel_user"]
    assert _preferred_panel_identity(owner, [owned, external]) == "duplicate"
    assert _preferred_panel_identity(owner, [external, owned]) == "duplicate"
    second = {**external, "uuid": "other", "username": "another_manual"}
    assert _preferred_panel_identity(owner, [owned, external, second]) is None
    assert _preferred_panel_identity(owner, [owned, {**external, "username": None}]) is None


@pytest.mark.parametrize("failed_step", ["update", "delete"])
def test_replacement_retry_keeps_new_paid_limits_and_panel_squads(duplicate_case, failed_step):
    case = duplicate_case
    case.target.traffic_limit_bytes = 777
    case.target.hwid_device_limit = 6
    case.kwargs["keep_panel_user"]["activeInternalSquads"] = ["old-plan"]
    case.kwargs["preserve_duplicate_identity"] = True
    if failed_step == "update":
        case.panel.update_user_details_on_panel.return_value = None
    else:
        case.panel.delete_user_from_panel.return_value = False
    assert not case.absorb()["resolved"]
    original = case.kwargs["keep_panel_user"]
    survivor = case.kwargs["duplicate_panel_user"]
    case.target.traffic_limit_bytes = 999
    case.target.hwid_device_limit = 10
    case.target.extra_hwid_devices = 2
    survivor["activeInternalSquads"] = ["new-paid-plan"]
    survivor["status"] = "DISABLED"
    case.target.is_active = False
    case.target.status_from_panel = "DISABLED"
    cancelled_end = case.now - timedelta(days=1)
    case.target.end_date = cancelled_end
    case.kwargs.update(
        {
            "keep_panel_uuid": "duplicate",
            "keep_panel_user": survivor,
            "duplicate_panel_user": original,
            "preserve_duplicate_identity": False,
        }
    )
    case.panel.delete_user_from_panel.return_value = True
    case.panel.update_user_details_on_panel.return_value = {"uuid": "duplicate"}
    assert case.absorb()["resolved"]
    payload = case.panel.update_user_details_on_panel.await_args.args[1]
    assert payload["trafficLimitBytes"] == 999
    assert payload["hwidDeviceLimit"] == 12
    if failed_step == "delete":
        assert payload["activeInternalSquads"] == ["new-paid-plan"]
        assert survivor["activeInternalSquads"] == ["new-paid-plan"]
    assert payload["status"] == "DISABLED"
    assert not case.target.is_active
    assert case.target.end_date == cancelled_end
    assert payload["expireAt"] == cancelled_end.isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def test_external_replacement_restores_missing_local_active_subscription(duplicate_case):
    case = duplicate_case
    case.subscriptions.pop("sub-keep")
    case.kwargs["duplicate_panel_user"]["status"] = "DISABLED"
    case.kwargs["preserve_duplicate_identity"] = True
    assert case.absorb()["resolved"]
    restored = case.subscriptions["sub-duplicate"]
    assert restored.is_active
    assert restored.end_date == case.target.end_date
    assert restored.panel_user_uuid == "duplicate"
    assert case.panel.update_user_details_on_panel.await_args.args[1]["status"] == "ACTIVE"


@pytest.mark.parametrize("configured,expected", [(None, "WEEK"), ("DAY", "DAY")])
def test_replacement_traffic_strategy_uses_current_tariff_or_settings(
    duplicate_case, configured, expected
):
    case = duplicate_case
    settings = case.kwargs["settings"]
    settings.USER_TRAFFIC_STRATEGY = "WEEK"
    settings.tariffs_config = TariffsConfig.model_validate(
        {
            "default_tariff": "plan",
            "tariffs": [
                {
                    "key": "plan",
                    "billing_model": "period",
                    "monthly_gb": 100,
                    "prices_rub": {"1": 100},
                    "enabled_periods": [1],
                    "traffic_limit_strategy": configured,
                }
            ],
        }
    )
    case.target.tariff_key = "plan"
    payload = asyncio.run(
        _local_replacement_limits(
            case.session,
            case.target,
            panel_uuid="keep",
            settings=settings,
            fallback_panel={"trafficLimitStrategy": "MONTH"},
        )
    )
    assert payload["trafficLimitStrategy"] == expected
    case.target.provider = "trial"
    trial = asyncio.run(
        _local_replacement_limits(
            case.session,
            case.target,
            panel_uuid="keep",
            settings=settings,
            fallback_panel={"trafficLimitStrategy": "MONTH"},
        )
    )
    assert trial["trafficLimitStrategy"] == "NO_RESET"


@pytest.mark.parametrize("duplicate_first", [False, True])
@pytest.mark.parametrize("batch_size", [1, 100])
def test_sync_automatically_merges_same_telegram_panel_records(duplicate_first, batch_size):
    expiry = "2027-01-01T00:00:00Z"
    primary = {
        "uuid": "keep",
        "shortUuid": "sub-keep",
        "username": "ms_primary",
        "telegramId": 123456789,
        "status": "ACTIVE",
        "expireAt": expiry,
    }
    duplicate = {
        **primary,
        "uuid": "duplicate",
        "shortUuid": "sub-duplicate",
        "username": "manually_created",
    }
    user = SimpleNamespace(
        user_id=42,
        panel_user_uuid="keep",
        panel_origin=panel_origin_fingerprint("https://panel.example.test/api"),
        panel_username="ms_primary",
        minishop_id="ms_primary",
        telegram_id=123456789,
        email=None,
        username=None,
        first_name=None,
        last_name=None,
        lifetime_used_traffic_bytes=None,
    )
    subscription = SimpleNamespace(
        subscription_id=10,
        user_id=42,
        panel_user_uuid="keep",
        is_active=True,
        end_date=datetime(2027, 1, 1, tzinfo=UTC),
    )
    indexes = {
        "users_by_telegram_id": {123456789: user},
        "users_by_user_id": {42: user},
        "users_by_panel_uuid": {"keep": user},
        "users_by_email": {},
        "subscriptions_by_panel_uuid": {},
        "active_subscriptions_by_user_panel": {},
        "subscriptions_by_user_panel": {},
    }
    merge = AsyncMock(
        return_value={"resolved": True, "subscriptions_created": 0, "subscriptions_updated": 0}
    )
    with (
        patch("bot.handlers.admin.sync_admin_runner.PANEL_SYNC_TRANSACTION_BATCH_SIZE", batch_size),
        patch(
            "bot.handlers.admin.sync_admin_runner.capture_subscription_snapshot",
            AsyncMock(return_value=None),
        ),
        patch(
            "bot.handlers.admin.sync_admin_runner.acquire_subscription_background_sync_lock",
            AsyncMock(),
        ),
        patch(
            "bot.handlers.admin.sync_admin_runner._prefetch_sync_indexes",
            AsyncMock(return_value=indexes),
        ),
        patch(
            "bot.handlers.admin.sync_admin_runner._merge_local_duplicate_panel_user_if_needed",
            AsyncMock(return_value=(user, True)),
        ),
        patch("bot.handlers.admin.sync_admin_runner._absorb_duplicate_panel_identity", merge),
        patch(
            "bot.handlers.admin.sync_admin_runner._panel_identity_view_for_comparison",
            AsyncMock(return_value=(primary, True)),
        ),
        patch(
            "bot.handlers.admin.sync_admin_runner._panel_identity_matches_user", return_value=True
        ),
        patch(
            "bot.handlers.admin.sync_admin_runner.subscription_dal.upsert_subscription",
            AsyncMock(return_value=subscription),
        ),
        patch(
            "bot.handlers.admin.sync_admin_runner.panel_sync_dal.update_panel_sync_status",
            AsyncMock(),
        ),
    ):
        result = asyncio.run(
            _perform_sync_impl(
                panel_service=SimpleNamespace(
                    get_all_panel_users=AsyncMock(
                        return_value=[duplicate, primary]
                        if duplicate_first
                        else [primary, duplicate]
                    )
                ),
                session=SimpleNamespace(
                    execute=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock()
                ),
                settings=SimpleNamespace(
                    PANEL_API_URL="https://panel.example.test/api",
                    DEFAULT_LANGUAGE="ru",
                    user_traffic_limit_bytes=0,
                ),
                i18n_instance=JsonI18n("locales", default="ru"),
            )
        )
    assert result["status"] == "completed", result["errors"]
    assert result["users_created"] == 0
    merge.assert_awaited_once()
    assert merge.await_args.kwargs["keep_panel_uuid"] == "keep"
    assert merge.await_args.kwargs["duplicate_panel_user"] == duplicate
    assert merge.await_args.kwargs["preserve_duplicate_identity"] is True
    assert user.panel_user_uuid == "keep"
    assert user.panel_username == "ms_primary"
