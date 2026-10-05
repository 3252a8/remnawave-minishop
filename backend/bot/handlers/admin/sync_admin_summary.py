from datetime import UTC, datetime
from typing import Any

from bot.middlewares.i18n import JsonI18n
from db.models import Subscription


def snapshot_is_newer(current_value: datetime | None, next_value: datetime) -> bool:
    if current_value is None:
        return True
    current = current_value.replace(tzinfo=UTC) if current_value.tzinfo is None else current_value
    next_connected = next_value.replace(tzinfo=UTC) if next_value.tzinfo is None else next_value
    return current.astimezone(UTC) < next_connected.astimezone(UTC)


def include_last_connected_snapshot(
    payload: dict[str, Any],
    subscription: Subscription | None,
    connected_at: datetime | None,
) -> None:
    if connected_at is None:
        return
    if subscription is None or snapshot_is_newer(subscription.last_connected_at, connected_at):
        payload["last_connected_at"] = connected_at


def localized_sync_details(
    i18n: JsonI18n,
    language: str,
    *,
    panel_records_checked: int,
    users_found_in_db: int,
    users_created: int,
    users_updated: int,
    subscriptions_synced_count: int,
    subscriptions_created: int,
    subscriptions_updated: int,
    users_without_telegram_id: int,
    users_not_found_in_db: int,
    error_count: int,
    users_skipped_no_identity: int = 0,
) -> str:
    additional_stats = ""
    if users_without_telegram_id > 0:
        additional_stats += i18n.gettext(
            language, "admin_sync_no_telegram_id", count=users_without_telegram_id
        )
    if users_not_found_in_db > 0:
        additional_stats += i18n.gettext(
            language, "admin_sync_not_found_in_db", count=users_not_found_in_db
        )
    if users_skipped_no_identity > 0:
        additional_stats += i18n.gettext(
            language, "admin_sync_skipped_no_identity", count=users_skipped_no_identity
        )
    if error_count:
        additional_stats += i18n.gettext(language, "admin_sync_errors", count=error_count)
    return i18n.gettext(
        language,
        "admin_sync_details",
        panel_records_checked=panel_records_checked,
        users_found_in_db=users_found_in_db,
        users_created=users_created,
        users_updated=users_updated,
        subscriptions_synced_count=subscriptions_synced_count,
        subscriptions_created=subscriptions_created,
        subscriptions_updated=subscriptions_updated,
        additional_stats=additional_stats,
    )
