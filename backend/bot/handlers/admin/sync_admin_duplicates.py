"""Reconcile duplicate native panel identities without replacing local entitlements."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_order_terms import gift_tariff
from bot.services.subscription_service_impl.squad_overrides import (
    normalize_panel_internal_squad_uuids,
)
from config.settings import Settings
from config.tariffs_config import TariffsConfig
from config.traffic_strategy import normalize_traffic_limit_strategy
from db.advisory_locks import commit_subscription_background_sync_batch
from db.dal import (
    subscription_dal,
    subscription_panel_identity_dal,
    tariff_dal,
    user_dal,
    user_panel_squad_override_dal,
)
from db.models import HwidDevicePurchase, Subscription, User, UserPanelSquadOverride

from .sync_admin_common import (
    _as_utc,
    _log_sync_panel_patch,
    _panel_expire_at,
    _panel_identity_fields_update_payload,
    _panel_subscription_uuid,
    _subscription_update_delta,
)

logger = logging.getLogger(__name__)


def _preferred_panel_identity(user: User, candidates: list[dict[str, Any]]) -> str | None:
    """Retain the unique externally named account; ambiguous identities need review."""
    if any(not candidate.get("username") for candidate in candidates):
        return None
    owned_names = {user.minishop_id}
    if user.telegram_id is not None:
        owned_names.add(f"tg_{user.telegram_id}")
    owned_names.add(f"em_{user.user_id}")
    external = [
        candidate
        for candidate in candidates
        if candidate.get("username") and candidate["username"] not in owned_names
    ]
    if len(external) == 1:
        return str(external[0]["uuid"])
    if external:
        return None
    return user.panel_user_uuid


def _replacement_panel_payload(panel_user: dict[str, Any]) -> dict[str, Any]:
    # Connection keys, native subscription links and username belong to the survivor.
    fields = (
        "trafficLimitBytes",
        "trafficLimitStrategy",
        "hwidDeviceLimit",
        "activeInternalSquads",
        "externalSquadUuid",
        "tag",
        "status",
    )
    return {field: panel_user[field] for field in fields if field in panel_user}


def _panel_identity_payload_with_expiry(
    user: User,
    *,
    expire_at: datetime,
) -> dict[str, Any]:
    payload = _panel_identity_fields_update_payload(user)
    payload["expireAt"] = expire_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if expire_at > datetime.now(UTC):
        payload["status"] = "ACTIVE"
    return payload


async def _local_replacement_limits(
    session: AsyncSession,
    target: Subscription,
    *,
    panel_uuid: str,
    settings: Settings,
    fallback_panel: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    traffic_limit = getattr(target, "traffic_limit_bytes", None)
    if traffic_limit is not None:
        payload["trafficLimitBytes"] = max(0, int(traffic_limit))
    device_limit = getattr(target, "hwid_device_limit", None)
    if device_limit is not None:
        base = max(0, int(device_limit))
        extra = max(0, int(getattr(target, "extra_hwid_devices", 0) or 0))
        if (
            isinstance(session, AsyncSession)
            and await session.scalar(
                select(HwidDevicePurchase.purchase_id)
                .where(HwidDevicePurchase.subscription_id == target.subscription_id)
                .limit(1)
            )
            is not None
        ):
            summary = await tariff_dal.get_hwid_device_entitlement_summary(
                session, subscription_id=target.subscription_id, include_future=False
            )
            extra = max(0, int(summary["active_devices"]))
        payload["hwidDeviceLimit"] = base + extra if base else 0
    tariff = gift_tariff(target)
    config = settings.tariffs_config
    if tariff is None and isinstance(config, TariffsConfig) and getattr(target, "tariff_key", None):
        try:
            tariff = config.require_configured(target.tariff_key)
        except ValueError:
            logger.warning(
                "Sync: no configured tariff for retained subscription %s", target.subscription_id
            )
    managed = normalize_panel_internal_squad_uuids(fallback_panel) or []
    trial = (
        str(getattr(target, "provider", "") or "").lower() == "trial"
        or str(target.status_from_panel or "").upper() == "TRIAL"
    )
    if trial:
        strategy = settings.TRIAL_TRAFFIC_STRATEGY
    elif tariff is not None and tariff.billing_model == "traffic":
        strategy = "NO_RESET"
    else:
        strategy = (
            tariff.traffic_limit_strategy if tariff else None
        ) or settings.USER_TRAFFIC_STRATEGY
    payload["trafficLimitStrategy"] = normalize_traffic_limit_strategy(strategy, default="MONTH")
    if tariff is not None:
        premium = set(tariff.premium_squad_uuids or [])
        include_premium = not bool(getattr(target, "premium_is_limited", False)) or bool(
            getattr(target, "premium_unlimited_override", False)
        )
        managed = [
            uuid for uuid in tariff.squad_uuids or [] if include_premium or uuid not in premium
        ]
        if include_premium:
            managed.extend(tariff.premium_squad_uuids or [])
    if isinstance(session, AsyncSession):
        tracked = (
            await session.scalars(
                select(UserPanelSquadOverride.squad_uuid).where(
                    UserPanelSquadOverride.user_id == target.user_id,
                    UserPanelSquadOverride.panel_user_uuid == panel_uuid,
                    UserPanelSquadOverride.kind == "internal",
                )
            )
        ).all()
        if tariff is None:
            # Explicitly removed manual membership must not return from a stale snapshot.
            managed = [uuid for uuid in managed if uuid not in tracked]
        manual = await user_panel_squad_override_dal.get_active_internal_squad_uuids(
            session,
            user_id=int(target.user_id),
            panel_user_uuid=panel_uuid,
        )
        external = await user_panel_squad_override_dal.get_active_external_override(
            session, user_id=int(target.user_id), panel_user_uuid=panel_uuid
        )
        if external is not None:
            payload["externalSquadUuid"] = external.squad_uuid if external.mode == "set" else None
    else:
        manual = []
    if "activeInternalSquads" in fallback_panel or tariff is not None or manual:
        payload["activeInternalSquads"] = list(
            dict.fromkeys(
                [
                    *managed,
                    *manual,
                ]
            )
        )
    return payload


async def _absorb_duplicate_panel_identity(
    session: AsyncSession,
    *,
    panel_service: PanelApiService,
    existing_user: User,
    keep_panel_uuid: str,
    keep_panel_user: dict[str, Any] | None,
    duplicate_panel_user: dict[str, Any],
    settings: Settings,
    subscriptions_by_panel_uuid: dict[str, Subscription],
    active_subscriptions_by_user_panel: dict[tuple[int, str], Subscription],
    preserve_duplicate_identity: bool = False,
) -> dict[str, int | bool | str]:
    duplicate_panel_uuid = str(duplicate_panel_user.get("uuid") or "")
    keep_subscription_uuid = _panel_subscription_uuid(keep_panel_user or {})
    duplicate_subscription_uuid = _panel_subscription_uuid(duplicate_panel_user)
    if (
        not duplicate_panel_uuid
        or not keep_subscription_uuid
        or not duplicate_subscription_uuid
        or duplicate_panel_uuid == keep_panel_uuid
        or duplicate_subscription_uuid == keep_subscription_uuid
    ):
        return {"resolved": False, "subscriptions_created": 0, "subscriptions_updated": 0}

    await user_dal.lock_user_entitlement(session, int(existing_user.user_id))
    if existing_user.panel_user_uuid != keep_panel_uuid:
        return {"resolved": False, "subscriptions_created": 0, "subscriptions_updated": 0}
    subscriptions_created = 0
    subscriptions_updated = 0
    panel_patches = 0
    now = datetime.now(UTC)
    duplicate_expire_at = _panel_expire_at(duplicate_panel_user)
    duplicate_status = str(duplicate_panel_user.get("status") or "").upper()
    duplicate_is_active = bool(
        duplicate_expire_at and duplicate_status == "ACTIVE" and duplicate_expire_at > now
    )

    target_sub = await subscription_dal.get_subscription_by_panel_subscription_uuid(
        session, keep_subscription_uuid
    )
    if not target_sub:
        target_sub = await subscription_dal.get_active_subscription_by_user_id(
            session,
            int(existing_user.user_id),
            keep_panel_uuid,
        )
    duplicate_sub = await subscription_dal.get_subscription_by_panel_subscription_uuid(
        session, duplicate_subscription_uuid
    )
    if target_sub is not None and target_sub is duplicate_sub:
        return {"resolved": False, "subscriptions_created": 0, "subscriptions_updated": 0}
    for subscription, expected_panel_uuid in (
        (target_sub, keep_panel_uuid),
        (duplicate_sub, duplicate_panel_uuid),
    ):
        if subscription is not None:
            await session.refresh(subscription)
            if (
                int(subscription.user_id) != int(existing_user.user_id)
                or subscription.panel_user_uuid != expected_panel_uuid
            ):
                return {"resolved": False, "subscriptions_created": 0, "subscriptions_updated": 0}
    if (
        preserve_duplicate_identity
        and target_sub
        and getattr(target_sub, "install_share_token", None)
        and not duplicate_panel_user.get("shortUuid")
    ):
        return {"resolved": False, "subscriptions_created": 0, "subscriptions_updated": 0}
    if preserve_duplicate_identity and target_sub is None:
        old_panel = keep_panel_user or {}
        old_expiry = _panel_expire_at(old_panel) or now
        old_status = str(old_panel.get("status") or "EXPIRED").upper()
        target_sub = await subscription_dal.upsert_subscription(
            session,
            {
                "user_id": int(existing_user.user_id),
                "panel_user_uuid": keep_panel_uuid,
                "panel_subscription_uuid": keep_subscription_uuid,
                "end_date": old_expiry,
                "is_active": old_status == "ACTIVE" and old_expiry > now,
                "status_from_panel": old_status,
                "traffic_limit_bytes": old_panel.get(
                    "trafficLimitBytes", settings.user_traffic_limit_bytes
                ),
                "hwid_device_limit": old_panel.get("hwidDeviceLimit"),
                "auto_renew_enabled": False,
            },
        )
        subscriptions_by_panel_uuid[keep_subscription_uuid] = target_sub
        subscriptions_created += 1

    final_end_date: datetime | None = None
    replacement_retry = bool(
        duplicate_sub
        and duplicate_sub.status_from_panel
        in {
            "MERGED_PANEL_REPLACED",
            "MERGED_PANEL_REPLACED_APPLIED",
        }
    )
    replacement_applied = bool(
        duplicate_sub and duplicate_sub.status_from_panel == "MERGED_PANEL_REPLACED_APPLIED"
    )
    already_transferred = bool(
        duplicate_sub
        and duplicate_sub.status_from_panel
        in {
            "MERGED_PANEL_DUPLICATE",
            "MERGED_PANEL_REPLACED",
            "MERGED_PANEL_REPLACED_APPLIED",
        }
    )
    has_transferred_period = bool(
        already_transferred and duplicate_sub and _as_utc(duplicate_sub.end_date) > now
    )
    if has_transferred_period or (
        not already_transferred and duplicate_is_active and duplicate_expire_at
    ):
        keep_end = _panel_expire_at(keep_panel_user or {}) or now
        base_end = max(now, keep_end, _as_utc(target_sub.end_date) if target_sub else now)
        if already_transferred and duplicate_sub:
            final_end_date = max(base_end, _as_utc(duplicate_sub.end_date))
        elif duplicate_expire_at:
            final_end_date = base_end + max(timedelta(0), duplicate_expire_at - now)
        if target_sub:
            update_payload: dict[str, Any] = {
                "user_id": int(existing_user.user_id),
                "panel_user_uuid": keep_panel_uuid,
                "end_date": final_end_date,
                "is_active": True,
                "status_from_panel": "ACTIVE_EXTENDED_BY_PANEL_DUPLICATE_MERGE",
            }
            if replacement_retry:
                update_payload["is_active"] = target_sub.is_active
                update_payload["status_from_panel"] = target_sub.status_from_panel
                if not target_sub.is_active:
                    final_end_date = _as_utc(target_sub.end_date)
                    update_payload["end_date"] = final_end_date
            if keep_subscription_uuid:
                update_payload["panel_subscription_uuid"] = keep_subscription_uuid
            update_delta = _subscription_update_delta(target_sub, update_payload)
            if update_delta:
                await subscription_dal.update_subscription(
                    session,
                    target_sub.subscription_id,
                    update_delta,
                )
                for key, value in update_delta.items():
                    setattr(target_sub, key, value)
                subscriptions_updated += 1
        else:
            created_sub = await subscription_dal.upsert_subscription(
                session,
                {
                    "user_id": int(existing_user.user_id),
                    "panel_user_uuid": keep_panel_uuid,
                    "panel_subscription_uuid": keep_subscription_uuid,
                    "start_date": None,
                    "end_date": final_end_date,
                    "duration_months": None,
                    "is_active": True,
                    "status_from_panel": "ACTIVE_EXTENDED_BY_PANEL_DUPLICATE_MERGE",
                    "traffic_limit_bytes": settings.user_traffic_limit_bytes,
                    "auto_renew_enabled": False,
                },
            )
            subscriptions_by_panel_uuid[keep_subscription_uuid] = created_sub
            active_subscriptions_by_user_panel[
                (int(created_sub.user_id), created_sub.panel_user_uuid)
            ] = created_sub
            subscriptions_created += 1
            target_sub = created_sub

    if replacement_retry and target_sub and not target_sub.is_active:
        final_end_date = _as_utc(target_sub.end_date)
    retained_panel_uuid = keep_panel_uuid
    retained_panel_user = keep_panel_user
    removed_panel_uuid = duplicate_panel_uuid
    panel_config = (
        _replacement_panel_payload(duplicate_panel_user)
        if replacement_retry and not replacement_applied
        else {}
    )
    receipt_status = (
        "MERGED_PANEL_REPLACED_APPLIED"
        if replacement_applied
        else "MERGED_PANEL_REPLACED"
        if replacement_retry
        else "MERGED_PANEL_DUPLICATE"
    )
    if preserve_duplicate_identity:
        # Free the survivor's UNIQUE native link before transferring the existing
        # subscription row. Its ID, tariff, payments and renewal consent stay intact.
        if duplicate_sub:
            await subscription_dal.update_subscription(
                session, duplicate_sub.subscription_id, {"panel_subscription_uuid": None}
            )
            duplicate_sub.panel_subscription_uuid = None
            await session.flush()
        if target_sub:
            relink_payload: dict[str, Any] = {
                "panel_user_uuid": duplicate_panel_uuid,
                "panel_subscription_uuid": duplicate_subscription_uuid,
            }
            if getattr(target_sub, "install_share_token", None):
                relink_payload["install_share_panel_short_uuid"] = (
                    str(duplicate_panel_user.get("shortUuid") or "").strip() or None
                )
            await subscription_dal.update_subscription(
                session,
                target_sub.subscription_id,
                relink_payload,
            )
            for key, value in relink_payload.items():
                setattr(target_sub, key, value)
            if final_end_date is None:
                final_end_date = max(
                    _as_utc(target_sub.end_date), _panel_expire_at(keep_panel_user or {}) or now
                )
        else:
            # Even an inactive external record receives the existing account's state.
            final_end_date = _panel_expire_at(keep_panel_user or {}) or now
        await subscription_panel_identity_dal.relink_panel_subscriptions(
            session,
            user_id=int(existing_user.user_id),
            old_panel_user_uuid=keep_panel_uuid,
            new_panel_user_uuid=duplicate_panel_uuid,
            panel_subscription_uuid=None,
        )
        await user_panel_squad_override_dal.merge_panel_user_uuid(
            session,
            user_id=int(existing_user.user_id),
            old_panel_user_uuid=keep_panel_uuid,
            new_panel_user_uuid=duplicate_panel_uuid,
        )
        existing_user.panel_user_uuid = duplicate_panel_uuid
        existing_user.panel_username = str(duplicate_panel_user["username"])
        existing_user.panel_username_state = "legacy_pending"
        retained_panel_uuid, removed_panel_uuid = duplicate_panel_uuid, keep_panel_uuid
        retained_panel_user = duplicate_panel_user
        panel_config = _replacement_panel_payload(keep_panel_user or {})
        receipt_status = "MERGED_PANEL_REPLACED"
        subscriptions_by_panel_uuid.pop(keep_subscription_uuid, None)
        subscriptions_by_panel_uuid.pop(duplicate_subscription_uuid, None)
        active_subscriptions_by_user_panel.pop((int(existing_user.user_id), keep_panel_uuid), None)
        if target_sub:
            subscriptions_by_panel_uuid[duplicate_subscription_uuid] = target_sub
            if target_sub.is_active:
                active_subscriptions_by_user_panel[
                    (int(existing_user.user_id), duplicate_panel_uuid)
                ] = target_sub

    # The inactive source row is the durable transfer receipt. Its end date
    # records the resulting expiry, so retries cannot add the same period twice,
    # even if a subsequent panel snapshot temporarily restores an older expiry.
    transfer_end_date = final_end_date or now
    source_payload = {
        "user_id": int(existing_user.user_id),
        "is_active": False,
        "skip_notifications": True,
        "status_from_panel": receipt_status,
        "end_date": transfer_end_date,
    }
    receipt_panel_uuid = keep_panel_uuid if preserve_duplicate_identity else duplicate_panel_uuid
    receipt_subscription_uuid = (
        keep_subscription_uuid if preserve_duplicate_identity else duplicate_subscription_uuid
    )
    source_payload.update(
        {
            "panel_user_uuid": receipt_panel_uuid,
            "panel_subscription_uuid": receipt_subscription_uuid,
        }
    )
    if duplicate_sub and duplicate_sub is not target_sub:
        await subscription_dal.update_subscription(
            session,
            duplicate_sub.subscription_id,
            source_payload,
        )
        for key, value in source_payload.items():
            setattr(duplicate_sub, key, value)
        subscriptions_updated += 1
    elif not duplicate_sub:
        duplicate_sub = await subscription_dal.upsert_subscription(
            session,
            {
                **source_payload,
                "auto_renew_enabled": False,
            },
        )
        subscriptions_created += 1
    if duplicate_sub:
        subscriptions_by_panel_uuid[receipt_subscription_uuid] = duplicate_sub

    # Persist the receipt before any external mutation. Reacquire the same
    # locks and reread the target so a concurrent payment is never overwritten.
    await commit_subscription_background_sync_batch(session)
    await user_dal.lock_user_entitlement(session, int(existing_user.user_id))
    if final_end_date and target_sub:
        await session.refresh(target_sub)
        final_end_date = (
            _as_utc(target_sub.end_date)
            if (preserve_duplicate_identity or replacement_retry) and not target_sub.is_active
            else max(final_end_date, _as_utc(target_sub.end_date))
        )

    if final_end_date:
        panel_payload = {
            **panel_config,
            **_panel_identity_payload_with_expiry(existing_user, expire_at=final_end_date),
        }
        if target_sub and not target_sub.is_active and "status" in panel_config:
            panel_payload["status"] = panel_config["status"]
        if (preserve_duplicate_identity or replacement_retry) and target_sub:
            panel_payload.update(
                await _local_replacement_limits(
                    session,
                    target_sub,
                    panel_uuid=retained_panel_uuid,
                    settings=settings,
                    fallback_panel=retained_panel_user or {}
                    if replacement_applied
                    else panel_config,
                )
            )
            if not target_sub.is_active:
                local_status = str(target_sub.status_from_panel or "DISABLED").upper()
                panel_payload["status"] = (
                    local_status
                    if local_status in {"DISABLED", "EXPIRED", "LIMITED"}
                    else "DISABLED"
                )
        _log_sync_panel_patch(
            source="duplicate_panel_merge",
            user=existing_user,
            panel_uuid=retained_panel_uuid,
            update_payload=panel_payload,
            current_panel_user=retained_panel_user,
            reasons=["duplicate_panel_merge_extend"],
            panel_view="list",
        )
        panel_patches += 1
        updated = await panel_service.update_user_details_on_panel(
            retained_panel_uuid,
            panel_payload,
            log_response=False,
        )
        if not updated:
            return {
                "resolved": False,
                "subscriptions_created": subscriptions_created,
                "subscriptions_updated": subscriptions_updated,
                "panel_patches": panel_patches,
            }
        if retained_panel_user is not None:
            retained_panel_user.update(panel_payload)
        if (preserve_duplicate_identity or replacement_retry) and duplicate_sub:
            await subscription_dal.update_subscription(
                session,
                duplicate_sub.subscription_id,
                {
                    "status_from_panel": "MERGED_PANEL_REPLACED_APPLIED",
                    "end_date": final_end_date,
                },
            )
            duplicate_sub.status_from_panel = "MERGED_PANEL_REPLACED_APPLIED"
            duplicate_sub.end_date = final_end_date
            await commit_subscription_background_sync_batch(session)
            await user_dal.lock_user_entitlement(session, int(existing_user.user_id))

    deleted = await panel_service.delete_user_from_panel(
        removed_panel_uuid,
        log_response=False,
    )
    if deleted:
        logger.info(
            "Sync: absorbed duplicate panel UUID %s into kept panel UUID %s for user %s.",
            removed_panel_uuid,
            retained_panel_uuid,
            existing_user.user_id,
        )
    else:
        logger.warning(
            "Sync: failed to delete duplicate panel UUID %s after absorbing it into %s.",
            removed_panel_uuid,
            retained_panel_uuid,
        )

    return {
        "resolved": bool(deleted),
        "subscriptions_created": subscriptions_created,
        "subscriptions_updated": subscriptions_updated,
        "panel_patches": panel_patches,
        "kept_panel_uuid": retained_panel_uuid,
        "deleted_panel_uuid": removed_panel_uuid,
    }
