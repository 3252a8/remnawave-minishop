import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from bot.infra import events
from bot.services.subscription_notification_worker import SubscriptionNotificationWorker
from db.dal import subscription_dal


def _worker(**overrides):
    settings_payload = {
        "SUBSCRIPTION_NOTIFY_DAYS_BEFORE": 3,
        "SUBSCRIPTION_NOTIFY_HOURS_BEFORE": 3,
        "SUBSCRIPTION_NOTIFY_ON_EXPIRE": True,
        "SUBSCRIPTION_NOTIFY_AFTER_EXPIRE": True,
        "SUBSCRIPTION_NOTIFICATION_WORKER_TICK_SECONDS": 300,
        **overrides,
    }
    settings = SimpleNamespace(**settings_payload)
    return SubscriptionNotificationWorker(
        settings=settings,
        session_factory=object(),
        bot=object(),
        i18n=object(),
        panel_service=object(),
        subscription_service=object(),
    )


def _sub(
    end_date,
    *,
    suppress_early_expiry_notifications=False,
    user_id=123,
    subscription_id=1,
    start_date=None,
    duration_months=None,
    provider=None,
    status_from_panel=None,
    tariff_key=None,
):
    return SimpleNamespace(
        end_date=end_date,
        suppress_early_expiry_notifications=suppress_early_expiry_notifications,
        user_id=user_id,
        subscription_id=subscription_id,
        start_date=start_date,
        duration_months=duration_months,
        provider=provider,
        status_from_panel=status_from_panel,
        tariff_key=tariff_key,
    )


def test_stage_prefers_hour_reminder_over_day_backlog():
    now = datetime(2026, 5, 28, 12, tzinfo=UTC)
    stage = _worker().stage_for_subscription(_sub(now + timedelta(hours=2, minutes=30)), now)

    assert stage.key == "before_3h"
    assert stage.message_key == "subscription_hours_notification"
    assert stage.hours_before == 3


def test_stage_uses_most_imminent_day_reminder():
    now = datetime(2026, 5, 28, 12, tzinfo=UTC)
    stage = _worker().stage_for_subscription(_sub(now + timedelta(hours=23)), now)

    assert stage.key == "before_1d"
    assert stage.message_key == "subscription_24h_notification"


def test_stage_sends_expired_during_first_day_after_end():
    now = datetime(2026, 5, 28, 12, tzinfo=UTC)
    stage = _worker().stage_for_subscription(_sub(now - timedelta(hours=1)), now)

    assert stage.key == "expired"
    assert stage.message_key == "subscription_expired_notification"


def test_stage_sends_yesterday_notice_only_after_first_day():
    now = datetime(2026, 5, 28, 12, tzinfo=UTC)
    stage = _worker().stage_for_subscription(_sub(now - timedelta(hours=25)), now)

    assert stage.key == "expired_24h_after"
    assert stage.message_key == "subscription_expired_yesterday_notification"


def test_promo_subscription_skips_day_before_reminders():
    now = datetime(2026, 5, 28, 12, tzinfo=UTC)
    sub = _sub(
        now + timedelta(hours=23),
        suppress_early_expiry_notifications=True,
        start_date=now - timedelta(days=2),
        status_from_panel="ACTIVE_BONUS",
    )

    assert _worker().stage_for_subscription(sub, now) is None


def test_extended_suppressed_subscription_gets_day_before_reminder():
    now = datetime(2026, 5, 28, 12, tzinfo=UTC)
    sub = _sub(
        now + timedelta(days=2, hours=23),
        suppress_early_expiry_notifications=True,
        start_date=now - timedelta(days=27),
        duration_months=0,
        status_from_panel="ACTIVE_EXTENDED_BY_BOT",
    )
    stage = _worker().stage_for_subscription(sub, now)

    assert stage.key == "before_3d"
    assert stage.message_key == "subscription_72h_notification"


def test_paid_subscription_with_stale_suppression_gets_day_before_reminder():
    now = datetime(2026, 5, 28, 12, tzinfo=UTC)
    sub = _sub(
        now + timedelta(hours=23),
        suppress_early_expiry_notifications=True,
        duration_months=1,
    )
    stage = _worker().stage_for_subscription(sub, now)

    assert stage.key == "before_1d"
    assert stage.message_key == "subscription_24h_notification"


def test_promo_subscription_still_gets_hours_before_reminder():
    now = datetime(2026, 5, 28, 12, tzinfo=UTC)
    sub = _sub(now + timedelta(hours=2, minutes=30), suppress_early_expiry_notifications=True)
    stage = _worker().stage_for_subscription(sub, now)

    assert stage.key == "before_3h"
    assert stage.hours_before == 3


def test_promo_subscription_still_gets_expiry_notice():
    now = datetime(2026, 5, 28, 12, tzinfo=UTC)
    sub = _sub(now - timedelta(hours=1), suppress_early_expiry_notifications=True)
    stage = _worker().stage_for_subscription(sub, now)

    assert stage.key == "expired"
    assert stage.message_key == "subscription_expired_notification"


def test_expired_row_superseded_when_user_has_newer_active_subscription():
    now = datetime(2026, 5, 28, 12, tzinfo=UTC)
    sub = _sub(now - timedelta(hours=25), user_id=555, subscription_id=244)
    # The user renewed into another active row that runs well into the future.
    latest_active = {555: now + timedelta(days=29)}

    assert _worker()._superseded_by_active_subscription(sub, latest_active, now) is True


def test_single_live_row_is_not_treated_as_superseded():
    now = datetime(2026, 5, 28, 12, tzinfo=UTC)
    sub = _sub(now + timedelta(hours=23), user_id=555, subscription_id=244)
    # The only active coverage is this very row, so the "ending soon" reminder
    # must still go out.
    latest_active = {555: sub.end_date}

    assert _worker()._superseded_by_active_subscription(sub, latest_active, now) is False


def test_expired_row_without_other_coverage_is_not_superseded():
    now = datetime(2026, 5, 28, 12, tzinfo=UTC)
    sub = _sub(now - timedelta(hours=25), user_id=555, subscription_id=244)

    assert _worker()._superseded_by_active_subscription(sub, {}, now) is False


def test_expired_event_stage_ignores_delivery_flags():
    now = datetime(2026, 5, 28, 12, tzinfo=UTC)
    worker = _worker(
        SUBSCRIPTION_NOTIFY_ON_EXPIRE=False,
        SUBSCRIPTION_NOTIFY_AFTER_EXPIRE=False,
    )

    assert worker.stage_for_subscription(_sub(now - timedelta(hours=1)), now) is None
    expired_stage = worker.stage_for_subscription(
        _sub(now - timedelta(hours=1)),
        now,
        respect_delivery_flags=False,
    )
    lapsed_stage = worker.stage_for_subscription(
        _sub(now - timedelta(hours=25)),
        now,
        respect_delivery_flags=False,
    )
    assert expired_stage is not None
    assert lapsed_stage is not None
    assert expired_stage.key == "expired"
    assert lapsed_stage.key == "expired_24h_after"


def test_expiry_event_is_recorded_with_event_channel(monkeypatch):
    now = datetime(2026, 5, 28, 12, tzinfo=UTC)
    worker = _worker()
    sub = _sub(now - timedelta(hours=1), user_id=55, subscription_id=44, tariff_key="pro")
    stage = worker.stage_for_subscription(sub, now, respect_delivery_flags=False)
    assert stage is not None
    recorded = []
    emitted = []

    async def fake_has_notification(session, subscription_id, notification_key):
        return False

    async def fake_record_notification(session, subscription_id, notification_key, *, sent_at):
        recorded.append((subscription_id, notification_key, sent_at))

    async def fake_emit_model(payload):
        emitted.append(payload)

    monkeypatch.setattr(
        subscription_dal,
        "has_subscription_notification",
        fake_has_notification,
    )
    monkeypatch.setattr(
        subscription_dal,
        "record_subscription_notification",
        fake_record_notification,
    )
    monkeypatch.setattr(events, "emit_model", fake_emit_model)

    asyncio.run(worker._emit_expiry_event_once(object(), sub, stage, now))

    assert recorded == [(44, "expired:event", now)]
    assert len(emitted) == 1
    assert emitted[0].EVENT_NAME == events.SUBSCRIPTION_EXPIRED
    assert emitted[0].user_id == 55
    assert emitted[0].subscription_id == 44
    assert emitted[0].tariff_key == "pro"
