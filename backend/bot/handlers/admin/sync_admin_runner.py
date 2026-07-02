import logging
from collections import Counter
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.panel_api_service import PanelApiService
from config.settings import Settings
from db.advisory_locks import acquire_subscription_background_sync_lock
from db.dal import panel_sync_dal, subscription_dal, user_dal
from db.models import Subscription, User

from .sync_admin_common import (
    _append_unique,
    _coerce_panel_telegram_id,
    _description_contains_email,
    _description_without_email,
    _format_counter,
    _identity_panel_update_reasons,
    _log_sync_panel_patch,
    _normalize_panel_email,
    _panel_description_for_user,
    _panel_identity_fields_update_payload,
    _panel_identity_matches_user,
    _panel_identity_view_for_comparison,
    _panel_update_changes,
    _should_update_lifetime_used_traffic,
    _subscription_update_delta,
    _sync_lock,
)
from .sync_admin_identity import (
    _absorb_duplicate_panel_identity,
    _bind_panel_email_to_user,
    _extract_lifetime_used_traffic_bytes,
    _merge_local_duplicate_panel_user_if_needed,
    _prefetch_sync_indexes,
)


async def perform_sync(
    panel_service: PanelApiService,
    session: AsyncSession,
    settings: Settings,
    i18n_instance: JsonI18n,
) -> dict:
    """Single-flight entry point — skips when another sync is already running."""
    if _sync_lock.locked():
        logging.info("perform_sync: skipped because another sync is already in progress")
        return {
            "status": "skipped",
            "details": "Another sync run is already in progress.",
            "errors": [],
            "users_processed": 0,
            "subs_synced": 0,
        }
    async with _sync_lock:
        return await _perform_sync_impl(
            panel_service=panel_service,
            session=session,
            settings=settings,
            i18n_instance=i18n_instance,
        )


async def _perform_sync_impl(
    panel_service: PanelApiService,
    session: AsyncSession,
    settings: Settings,
    i18n_instance: JsonI18n,
) -> dict:
    """
    Perform panel synchronization and return results
    Returns dict with status, details, and sync statistics
    """
    panel_records_checked = 0
    users_found_in_db = 0
    users_updated = 0
    subscriptions_synced_count = 0
    sync_errors = []

    # Additional counters for detailed logging
    users_without_telegram_id = 0
    users_not_found_in_db = 0
    users_created = 0
    users_uuid_updated = 0
    subscriptions_created = 0
    subscriptions_updated = 0
    local_update_reason_counts: Counter[str] = Counter()
    panel_patch_reason_counts: Counter[str] = Counter()
    panel_patch_field_counts: Counter[str] = Counter()
    panel_patch_count = 0

    try:
        panel_users_data = await panel_service.get_all_panel_users()

        if panel_users_data is None:
            error_msg = "Failed to fetch users from panel or panel API issue."
            sync_errors.append(error_msg)
            await panel_sync_dal.update_panel_sync_status(session, "failed", error_msg)
            await session.commit()
            return {"status": "failed", "details": error_msg, "errors": sync_errors}

        if not panel_users_data:
            status_msg = "No users found in the panel to sync."
            await panel_sync_dal.update_panel_sync_status(session, "success", status_msg, 0, 0)
            await session.commit()
            return {
                "status": "success",
                "details": status_msg,
                "users_synced": 0,
                "subs_synced": 0,
            }

        total_panel_users = len(panel_users_data)
        logging.info(f"Starting sync for {total_panel_users} panel users.")
        await acquire_subscription_background_sync_lock(session)
        sync_indexes = await _prefetch_sync_indexes(session, panel_users_data)
        users_by_telegram_id = cast(dict[int, User], sync_indexes["users_by_telegram_id"])
        users_by_user_id = cast(dict[int, User], sync_indexes["users_by_user_id"])
        users_by_panel_uuid = cast(dict[str, User], sync_indexes["users_by_panel_uuid"])
        users_by_email = cast(dict[str, User], sync_indexes["users_by_email"])
        subscriptions_by_panel_uuid = cast(
            dict[str, Subscription],
            sync_indexes["subscriptions_by_panel_uuid"],
        )
        active_subscriptions_by_user_panel = cast(
            dict[tuple[int, str], Subscription],
            sync_indexes["active_subscriptions_by_user_panel"],
        )
        panel_uuids_by_telegram_id = cast(
            dict[int, set[str]],
            sync_indexes["panel_uuids_by_telegram_id"],
        )
        panel_users_by_uuid = {
            str(panel_user["uuid"]): panel_user
            for panel_user in panel_users_data
            if panel_user.get("uuid")
        }

        for panel_user_dict in panel_users_data:
            try:
                panel_records_checked += 1
                panel_uuid = panel_user_dict.get("uuid")
                panel_user_dict.get("subscriptionUuid") or panel_user_dict.get("shortUuid")
                telegram_id_from_panel = _coerce_panel_telegram_id(
                    panel_user_dict.get("telegramId")
                )
                email_from_panel = _normalize_panel_email(panel_user_dict.get("email"))

                if not panel_uuid:
                    sync_errors.append(f"Panel user missing UUID: {panel_user_dict}")
                    logging.warning(f"Skipping panel user without UUID: {panel_user_dict}")
                    continue

                # Track users without telegram ID
                if not telegram_id_from_panel:
                    users_without_telegram_id += 1

                # Try to find existing user in local DB
                existing_user = None

                # First, try to find by telegram ID if available
                if telegram_id_from_panel:
                    existing_user = users_by_telegram_id.get(
                        telegram_id_from_panel
                    ) or users_by_user_id.get(telegram_id_from_panel)
                    if existing_user:
                        logging.debug(f"Found user by telegramId {telegram_id_from_panel}")

                # If not found by telegram ID, try to find by panel UUID.
                # The panel UUID is the strongest local link for subscription sync.
                if not existing_user:
                    existing_user = users_by_panel_uuid.get(panel_uuid)
                    if existing_user:
                        logging.debug(
                            f"Found user by panel UUID {panel_uuid}, telegramId: {existing_user.user_id}"  # noqa: E501
                        )
                        # Update telegram ID if it was missing in panel data but we have local user
                        if (
                            telegram_id_from_panel
                            and existing_user.user_id != telegram_id_from_panel
                        ):
                            logging.warning(
                                f"TelegramId mismatch: panel={telegram_id_from_panel}, local={existing_user.user_id}"  # noqa: E501
                            )

                # Finally, fall back to email. This mainly catches panel users that
                # were first imported as email-only identities.
                if not existing_user and email_from_panel:
                    existing_user = users_by_email.get(email_from_panel)
                    if existing_user:
                        logging.debug(f"Found user by email {email_from_panel}")

                if not existing_user:
                    users_not_found_in_db += 1
                    if telegram_id_from_panel:
                        # Create new user if they have telegram_id
                        try:
                            user_data = {
                                "user_id": telegram_id_from_panel,
                                "telegram_id": telegram_id_from_panel,
                                "email": email_from_panel,
                                "email_verified_at": (
                                    datetime.now(UTC) if email_from_panel else None
                                ),
                                "username": None,  # Username will be updated when user interacts with bot  # noqa: E501
                                "first_name": None,  # Panel doesn't provide this info
                                "last_name": None,  # Panel doesn't provide this info
                                "language_code": "ru",  # Default language
                                "panel_user_uuid": panel_uuid,
                                "is_banned": False,
                                "referred_by_id": None,
                            }

                            new_user, was_created = await user_dal.create_user(
                                session, user_data, registered_via="panel_sync"
                            )
                            if was_created:
                                users_created += 1
                                logging.info(
                                    f"Created new user {telegram_id_from_panel} from panel sync with UUID {panel_uuid}"  # noqa: E501
                                )

                            existing_user = new_user
                            users_by_user_id[int(new_user.user_id)] = new_user
                            if new_user.telegram_id is not None:
                                users_by_telegram_id[int(new_user.telegram_id)] = new_user
                            users_by_panel_uuid[panel_uuid] = new_user
                            if email_from_panel:
                                users_by_email[email_from_panel] = new_user

                        except Exception as e_create:
                            sync_errors.append(
                                f"Error creating user {telegram_id_from_panel}: {str(e_create)}"
                            )
                            logging.error(
                                f"Error creating user {telegram_id_from_panel}: {e_create}"
                            )
                            continue
                    elif email_from_panel:
                        try:
                            new_user, was_created = await user_dal.create_email_user(
                                session,
                                email=email_from_panel,
                                language_code="ru",
                                registered_via="panel_sync",
                            )
                            new_user.panel_user_uuid = panel_uuid
                            if was_created:
                                users_created += 1
                                logging.info(
                                    f"Created new email user {new_user.user_id} from panel sync with UUID {panel_uuid}"  # noqa: E501
                                )
                            existing_user = new_user
                            users_by_user_id[int(new_user.user_id)] = new_user
                            users_by_panel_uuid[panel_uuid] = new_user
                            users_by_email[email_from_panel] = new_user
                        except Exception as e_create_email:
                            sync_errors.append(
                                f"Error creating email user {email_from_panel}: {str(e_create_email)}"  # noqa: E501
                            )
                            logging.error(
                                f"Error creating email user {email_from_panel}: {e_create_email}"
                            )
                            continue
                    else:
                        logging.debug(
                            f"Panel user with UUID {panel_uuid} (no telegramId) not found in local DB - skipping"  # noqa: E501
                        )
                        continue

                # User found in local DB
                users_found_in_db += 1
                user_was_updated = False
                user_update_reasons: list[str] = []

                # Get the actual user_id for subscription operations
                actual_user_id = existing_user.user_id
                is_duplicate_panel_identity = False

                # Update panel UUID if different
                if existing_user.panel_user_uuid != panel_uuid:
                    linked_uuid = existing_user.panel_user_uuid
                    linked_uuid_still_present = bool(
                        telegram_id_from_panel
                        and linked_uuid
                        and str(linked_uuid)
                        in panel_uuids_by_telegram_id.get(telegram_id_from_panel, set())
                    )
                    linked_uuid_present_on_panel = bool(
                        linked_uuid and str(linked_uuid) in panel_users_by_uuid
                    )
                    panel_uuid_owner = users_by_panel_uuid.get(panel_uuid)
                    if (
                        panel_uuid_owner
                        and panel_uuid_owner.user_id != existing_user.user_id
                        and not linked_uuid_still_present
                    ):
                        if linked_uuid_present_on_panel:
                            msg = (
                                f"Panel UUID {panel_uuid} for user {actual_user_id} is already "
                                f"linked to local user {panel_uuid_owner.user_id}, while current "
                                f"local panel UUID {linked_uuid} still exists on panel."
                            )
                            sync_errors.append(msg)
                            logging.warning("Sync: %s", msg)
                            continue

                        previous_panel_uuid = existing_user.panel_user_uuid
                        previous_owner_user_id = panel_uuid_owner.user_id
                        previous_owner_email = panel_uuid_owner.email
                        previous_owner_telegram_id = panel_uuid_owner.telegram_id
                        (
                            existing_user,
                            can_merge_panel_uuid_owner,
                        ) = await _merge_local_duplicate_panel_user_if_needed(
                            session,
                            existing_user=existing_user,
                            duplicate_panel_uuid=panel_uuid,
                        )
                        if not can_merge_panel_uuid_owner:
                            logging.warning(
                                "Sync: panel UUID %s is already linked to local user %s; "
                                "skipping reassignment to user %s because local merge failed.",
                                panel_uuid,
                                previous_owner_user_id,
                                actual_user_id,
                            )
                            continue

                        existing_user.panel_user_uuid = panel_uuid
                        actual_user_id = existing_user.user_id
                        user_was_updated = True
                        _append_unique(
                            user_update_reasons,
                            "panel_uuid_reassigned_after_local_merge",
                        )
                        users_uuid_updated += 1
                        if previous_panel_uuid:
                            users_by_panel_uuid.pop(str(previous_panel_uuid), None)
                        users_by_panel_uuid[panel_uuid] = existing_user
                        users_by_user_id.pop(int(previous_owner_user_id), None)
                        users_by_user_id[int(existing_user.user_id)] = existing_user
                        if previous_owner_telegram_id is not None:
                            users_by_telegram_id.pop(int(previous_owner_telegram_id), None)
                        if existing_user.telegram_id is not None:
                            users_by_telegram_id[int(existing_user.telegram_id)] = existing_user
                        if previous_owner_email:
                            users_by_email.pop(previous_owner_email.strip().lower(), None)
                        if existing_user.email:
                            users_by_email[existing_user.email.strip().lower()] = existing_user
                        logging.info(
                            "Sync: merged local user %s owning panel UUID %s into user %s "
                            "and reassigned stale local panel UUID %s.",
                            previous_owner_user_id,
                            panel_uuid,
                            actual_user_id,
                            previous_panel_uuid,
                        )
                    if linked_uuid_still_present:
                        is_duplicate_panel_identity = True
                        (
                            existing_user,
                            can_absorb_duplicate_panel_user,
                        ) = await _merge_local_duplicate_panel_user_if_needed(
                            session,
                            existing_user=existing_user,
                            duplicate_panel_uuid=panel_uuid,
                        )
                        if not can_absorb_duplicate_panel_user:
                            logging.warning(
                                "Sync: duplicate panel users share telegramId %s; keeping local panel UUID %s and skipping duplicate panel UUID %s because local duplicate merge failed.",  # noqa: E501
                                telegram_id_from_panel,
                                linked_uuid,
                                panel_uuid,
                            )
                            continue
                        actual_user_id = existing_user.user_id
                        users_by_panel_uuid[linked_uuid] = existing_user
                        if existing_user.telegram_id is not None:
                            users_by_telegram_id[int(existing_user.telegram_id)] = existing_user
                        users_by_user_id[int(existing_user.user_id)] = existing_user
                        if existing_user.email:
                            users_by_email[existing_user.email.strip().lower()] = existing_user
                        merge_result = await _absorb_duplicate_panel_identity(
                            session,
                            panel_service=panel_service,
                            existing_user=existing_user,
                            keep_panel_uuid=str(linked_uuid),
                            keep_panel_user=panel_users_by_uuid.get(str(linked_uuid)),
                            duplicate_panel_user=panel_user_dict,
                            settings=settings,
                            subscriptions_by_panel_uuid=subscriptions_by_panel_uuid,
                            active_subscriptions_by_user_panel=(active_subscriptions_by_user_panel),
                        )
                        subscriptions_created += int(merge_result["subscriptions_created"])
                        subscriptions_updated += int(merge_result["subscriptions_updated"])
                        subscriptions_synced_count += int(
                            merge_result["subscriptions_created"]
                        ) + int(merge_result["subscriptions_updated"])
                        merge_panel_patches = int(merge_result.get("panel_patches", 0))
                        if merge_panel_patches:
                            panel_patch_count += merge_panel_patches
                            panel_patch_reason_counts["duplicate_panel_merge_extend"] += (
                                merge_panel_patches
                            )
                        if merge_result["resolved"]:
                            users_updated += 1
                            users_uuid_updated += 1
                            local_update_reason_counts.update(["duplicate_panel_identity_resolved"])
                            if telegram_id_from_panel is not None:
                                panel_uuids_by_telegram_id.get(
                                    telegram_id_from_panel,
                                    set(),
                                ).discard(str(panel_uuid))
                            users_by_panel_uuid.pop(str(panel_uuid), None)
                            logging.info(
                                "Sync local update: user_id=%s telegram_id=%s panel_uuid=%s "
                                "reasons=%s",
                                actual_user_id,
                                existing_user.telegram_id,
                                linked_uuid,
                                "duplicate_panel_identity_resolved",
                            )
                        logging.warning(
                            "Sync: duplicate panel users share telegramId %s; kept local panel UUID %s and processed duplicate panel UUID %s.",  # noqa: E501
                            telegram_id_from_panel,
                            linked_uuid,
                            panel_uuid,
                        )
                        continue
                    elif existing_user.panel_user_uuid != panel_uuid:
                        existing_user.panel_user_uuid = panel_uuid
                        user_was_updated = True
                        _append_unique(user_update_reasons, "panel_uuid_synced")
                        users_uuid_updated += 1
                        users_by_panel_uuid[panel_uuid] = existing_user
                        logging.info(f"Updated panel UUID for user {actual_user_id}: {panel_uuid}")
                if not is_duplicate_panel_identity:
                    existing_user, email_was_bound = await _bind_panel_email_to_user(
                        session,
                        existing_user=existing_user,
                        email_from_panel=email_from_panel,
                        panel_uuid=panel_uuid,
                    )
                    if email_was_bound:
                        user_was_updated = True
                        _append_unique(user_update_reasons, "email_bound_from_panel")
                        if email_from_panel:
                            users_by_email[email_from_panel] = existing_user
                    if (
                        telegram_id_from_panel
                        and existing_user.telegram_id != telegram_id_from_panel
                    ):
                        existing_user.telegram_id = telegram_id_from_panel
                        user_was_updated = True
                        _append_unique(user_update_reasons, "telegram_id_bound_from_panel")
                        users_by_telegram_id[telegram_id_from_panel] = existing_user

                lifetime_used = _extract_lifetime_used_traffic_bytes(panel_user_dict)
                if lifetime_used is not None and _should_update_lifetime_used_traffic(
                    existing_user,
                    lifetime_used,
                    now=datetime.now(UTC),
                    settings=settings,
                    is_duplicate_panel_identity=is_duplicate_panel_identity,
                ):
                    existing_user.lifetime_used_traffic_bytes = lifetime_used
                    existing_user.lifetime_used_traffic_synced_at = datetime.now(UTC)
                    user_was_updated = True
                    _append_unique(user_update_reasons, "lifetime_traffic_synced")

                # Keep structural identity fields in panel and clean legacy email from
                # description. Plain description text is intentionally not canonical.
                try:
                    if panel_uuid and existing_user and not is_duplicate_panel_identity:
                        description_text = _panel_description_for_user(existing_user)
                        desired_description = description_text.strip()
                        (
                            panel_user_for_identity,
                            missing_identity_fields_match,
                        ) = await _panel_identity_view_for_comparison(
                            panel_service,
                            panel_uuid,
                            panel_user_dict,
                            existing_user,
                            desired_description,
                        )
                        current_description = panel_user_for_identity.get("description")
                        description_has_email = _description_contains_email(
                            current_description,
                            existing_user.email,
                        )
                        identity_matches = _panel_identity_matches_user(
                            panel_user_for_identity,
                            existing_user,
                            "",
                            missing_identity_fields_match=missing_identity_fields_match,
                        )
                        panel_payload = _panel_identity_fields_update_payload(existing_user)
                        if description_has_email:
                            panel_payload["description"] = _description_without_email(
                                current_description,
                                existing_user.email,
                            )
                        if description_has_email or not identity_matches:
                            panel_changes = _panel_update_changes(
                                panel_user_for_identity,
                                panel_payload,
                            )
                            panel_reasons = _identity_panel_update_reasons(
                                panel_changes,
                                description_has_email=description_has_email,
                            )
                            changed_fields = _log_sync_panel_patch(
                                source="identity_sync",
                                user=existing_user,
                                panel_uuid=panel_uuid,
                                update_payload=panel_payload,
                                current_panel_user=panel_user_for_identity,
                                reasons=panel_reasons,
                                panel_view=(
                                    "list" if missing_identity_fields_match else "full_fetch"
                                ),
                            )
                            panel_patch_count += 1
                            panel_patch_reason_counts.update(panel_reasons)
                            panel_patch_field_counts.update(changed_fields)
                            await panel_service.update_user_details_on_panel(
                                panel_uuid,
                                panel_payload,
                            )
                except Exception as e_desc:
                    logging.warning(
                        f"Sync: Failed to update panel identity for panel user {panel_uuid} (tg {actual_user_id}): {e_desc}"  # noqa: E501
                    )

                # Sync subscription data
                panel_expire_at_iso = panel_user_dict.get("expireAt")
                panel_status = panel_user_dict.get("status", "UNKNOWN")

                if panel_expire_at_iso:
                    try:
                        panel_expire_at = datetime.fromisoformat(
                            panel_expire_at_iso.replace("Z", "+00:00")
                        )

                        # Prefer syncing by concrete subscription UUID (shortUuid/subscriptionUuid)
                        subscription_uuid_from_panel = panel_user_dict.get(
                            "subscriptionUuid"
                        ) or panel_user_dict.get("shortUuid")

                        if subscription_uuid_from_panel:
                            # Если панель говорит, что подписка ACTIVE — сначала деактивируем все другие активные  # noqa: E501
                            if panel_status == "ACTIVE":
                                await session.execute(
                                    update(Subscription)
                                    .where(
                                        Subscription.panel_user_uuid == panel_uuid,
                                        Subscription.is_active.is_(True),
                                        or_(
                                            Subscription.panel_subscription_uuid
                                            != subscription_uuid_from_panel,
                                            Subscription.panel_subscription_uuid.is_(None),
                                        ),
                                    )
                                    .values(
                                        is_active=False,
                                        status_from_panel="INACTIVE",
                                    )
                                )

                            # Try to find subscription by its panel_subscription_uuid first (idempotent)  # noqa: E501
                            existing_sub_by_uuid = subscriptions_by_panel_uuid.get(
                                subscription_uuid_from_panel
                            )

                            if existing_sub_by_uuid:
                                update_payload = {
                                    "user_id": actual_user_id,
                                    "panel_user_uuid": panel_uuid,
                                    "end_date": panel_expire_at,
                                    "is_active": panel_status == "ACTIVE",
                                    "status_from_panel": panel_status,
                                }
                                update_delta = _subscription_update_delta(
                                    existing_sub_by_uuid, update_payload
                                )
                                if update_delta:
                                    # Atomic update of changed relevant fields
                                    await subscription_dal.update_subscription(
                                        session,
                                        existing_sub_by_uuid.subscription_id,
                                        update_delta,
                                    )
                                    subscriptions_updated += 1
                                    user_was_updated = True
                                    _append_unique(user_update_reasons, "subscription_updated")
                                subscriptions_synced_count += 1
                                logging.debug(
                                    f"Synced existing subscription {existing_sub_by_uuid.subscription_id} "  # noqa: E501
                                    f"for user {actual_user_id}: expires {panel_expire_at}, status {panel_status}"  # noqa: E501
                                )
                            else:
                                # Create a new subscription only when we have a concrete subscription UUID  # noqa: E501
                                sub_payload = {
                                    "user_id": actual_user_id,
                                    "panel_user_uuid": panel_uuid,
                                    "panel_subscription_uuid": subscription_uuid_from_panel,
                                    # Do not guess precise start_date from panel; keep nullable
                                    "start_date": None,
                                    "end_date": panel_expire_at,
                                    "duration_months": None,
                                    "is_active": panel_status == "ACTIVE",
                                    "status_from_panel": panel_status,
                                    "traffic_limit_bytes": settings.user_traffic_limit_bytes,
                                    "auto_renew_enabled": False,
                                }
                                created_sub = await subscription_dal.upsert_subscription(
                                    session, sub_payload
                                )
                                subscriptions_by_panel_uuid[subscription_uuid_from_panel] = (
                                    created_sub
                                )
                                if created_sub.is_active and created_sub.end_date > datetime.now(
                                    UTC
                                ):
                                    active_subscriptions_by_user_panel[
                                        (int(created_sub.user_id), created_sub.panel_user_uuid)
                                    ] = created_sub
                                subscriptions_synced_count += 1
                                subscriptions_created += 1
                                user_was_updated = True
                                _append_unique(user_update_reasons, "subscription_created")
                                logging.debug(
                                    f"Created subscription {created_sub.subscription_id} "
                                    f"for user {actual_user_id} by panel_sub_uuid {subscription_uuid_from_panel}"  # noqa: E501
                                )
                        else:
                            # No subscription UUID from panel: only update an already active subscription for this user/panel UUID  # noqa: E501
                            active_sub = active_subscriptions_by_user_panel.get(
                                (actual_user_id, panel_uuid)
                            )
                            if active_sub:
                                update_payload = {
                                    "end_date": panel_expire_at,
                                    "is_active": panel_status == "ACTIVE",
                                    "status_from_panel": panel_status,
                                }
                                update_delta = _subscription_update_delta(
                                    active_sub, update_payload
                                )
                                if update_delta:
                                    await subscription_dal.update_subscription(
                                        session,
                                        active_sub.subscription_id,
                                        update_delta,
                                    )
                                    subscriptions_updated += 1
                                    user_was_updated = True
                                    _append_unique(user_update_reasons, "subscription_updated")
                                subscriptions_synced_count += 1
                                logging.debug(
                                    f"Updated active subscription {active_sub.subscription_id} "
                                    f"for user {actual_user_id}: expires {panel_expire_at}, status {panel_status}"  # noqa: E501
                                )
                            else:
                                # Without a concrete subscription UUID we avoid creating new records to keep sync idempotent  # noqa: E501
                                logging.debug(
                                    f"No subscriptionUuid for panel user {panel_uuid}; skipped creation for user {actual_user_id}"  # noqa: E501
                                )

                    except Exception as e:
                        sync_errors.append(
                            f"Error syncing subscription for user {actual_user_id}: {str(e)}"
                        )
                        logging.error(f"Error syncing subscription for user {actual_user_id}: {e}")

                if user_was_updated:
                    users_updated += 1
                    if not user_update_reasons:
                        user_update_reasons.append("unspecified")
                    local_update_reason_counts.update(user_update_reasons)
                    logging.info(
                        "Sync local update: user_id=%s telegram_id=%s panel_uuid=%s reasons=%s",
                        actual_user_id,
                        existing_user.telegram_id,
                        panel_uuid,
                        ",".join(user_update_reasons),
                    )

            except Exception as e_user:
                sync_errors.append(
                    f"Error processing panel user {panel_user_dict.get('uuid', 'unknown')}: {str(e_user)}"  # noqa: E501
                )
                logging.error(f"Error syncing user: {e_user}")

        # Update sync status
        status = "completed_with_errors" if sync_errors else "completed"
        # Build additional stats
        default_lang = settings.DEFAULT_LANGUAGE
        additional_stats = ""
        if users_without_telegram_id > 0:
            additional_stats += i18n_instance.gettext(
                default_lang,
                "admin_sync_no_telegram_id",
                count=users_without_telegram_id,
            )
        if users_not_found_in_db > 0:
            additional_stats += i18n_instance.gettext(
                default_lang,
                "admin_sync_not_found_in_db",
                count=users_not_found_in_db,
            )
        if sync_errors:
            additional_stats += i18n_instance.gettext(
                default_lang, "admin_sync_errors", count=len(sync_errors)
            )

        # Build full details using localization
        details = i18n_instance.gettext(
            default_lang,
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

        await panel_sync_dal.update_panel_sync_status(
            session,
            status,
            details,
            panel_records_checked,
            subscriptions_synced_count,
        )
        await session.commit()

        # Detailed logging summary
        logging.info("Sync completed - Summary:")
        logging.info(f"  Panel records checked: {panel_records_checked}")
        logging.info(f"  Users without telegramId: {users_without_telegram_id}")
        logging.info(f"  Users not found in local DB: {users_not_found_in_db}")
        logging.info(f"  Users found in local DB: {users_found_in_db}")
        logging.info(f"  Users created: {users_created}")
        logging.info(f"  Users with UUID updated: {users_uuid_updated}")
        logging.info(f"  Users updated overall: {users_updated}")
        logging.info("  Local update reasons: %s", _format_counter(local_update_reason_counts))
        logging.info(f"  Panel PATCHes from sync: {panel_patch_count}")
        logging.info("  Panel PATCH reasons: %s", _format_counter(panel_patch_reason_counts))
        logging.info("  Panel PATCH fields: %s", _format_counter(panel_patch_field_counts))
        logging.info(f"  Subscriptions total synced: {subscriptions_synced_count}")
        logging.info(f"  Subscriptions created: {subscriptions_created}")
        logging.info(f"  Subscriptions updated: {subscriptions_updated}")
        logging.info(f"  Sync errors: {len(sync_errors)}")

        return {
            "status": status,
            "details": details,
            "users_processed": panel_records_checked,
            "users_synced": users_found_in_db,
            "users_created": users_created,
            "subs_synced": subscriptions_synced_count,
            "errors": sync_errors,
        }

    except Exception as e_sync_global:
        await session.rollback()
        logging.error(f"Global error during sync: {e_sync_global}", exc_info=True)
        error_detail = f"Unexpected error during sync: {str(e_sync_global)}"

        await panel_sync_dal.update_panel_sync_status(
            session,
            "failed",
            error_detail,
            panel_records_checked,
            subscriptions_synced_count,
        )

        return {
            "status": "failed",
            "details": error_detail,
            "errors": [str(e_sync_global)],
        }
