"""Bedolaga VPN importer with inventory, idempotency and reconciliation."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text

from db.auth_models import UserEmailAddress, UserExternalIdentity
from db.balance_models import UserBalanceLedgerEntry
from db.gift_models import SubscriptionGift
from db.models import Payment, PromoCode, PromoCodeActivation, Subscription, User

from .bedolaga_data import (
    bedolaga_build_tariff_catalog,
    bedolaga_ledger_effect,
    bedolaga_panel_subscription_uuid,
    bedolaga_payment_status,
    bedolaga_target_user_id,
)
from .bedolaga_operations import _BedolagaOperationsSection
from .common import GIB, _as_utc, _json_dumps, _path_write_text, _to_float, _to_int, _truthy

SUPPORTED_REVISIONS = {"0110", "0118"}
REQUIRED_COLUMNS = {
    "users": {"id", "telegram_id", "balance_kopeks", "created_at"},
    "subscriptions": {"id", "user_id", "status", "end_date", "is_trial"},
    "transactions": {"id", "user_id", "type", "amount_kopeks", "is_completed"},
    "tariffs": {"id", "name", "period_prices", "traffic_limit_gb", "device_limit"},
}


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _string(value: Any, limit: int | None = None) -> str | None:
    result = str(value or "").strip()
    if not result:
        return None
    return result[:limit] if limit else result


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except ValueError:
            return []
        return decoded if isinstance(decoded, list) else []
    return []


async def _artifact(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    await _path_write_text(target, _json_dumps(payload) + "\n", encoding="utf-8")


class BedolagaImporter(_BedolagaOperationsSection):
    source_type = "bedolaga"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.summary.update(
            {
                "batch_size": self.batch_size,
                "gifts": defaultdict(int),
                "support": defaultdict(int),
                "advertising": defaultdict(int),
                "partners": defaultdict(int),
                "balance_ledger": defaultdict(int),
                "identity_conflicts": [],
                "blockers": [],
            }
        )
        self.inventory: dict[str, Any] = {}
        self.config_plan: dict[str, Any] = {"source": self.source_type, "changes": [], "manual": []}
        self.reconciliation: dict[str, Any] = {}
        self.source_balance_by_user: dict[int, int] = {}
        self.source_panel_by_user: dict[int, str] = {}
        self.ledger_effect_by_user: dict[int, int] = defaultdict(int)
        self.tariff_id_map: dict[int, str] = {}

    async def _source_revision(self) -> str | None:
        if "alembic_version" not in self.tables:
            return None
        result = await self.source.execute(
            text(f'SELECT version_num FROM "{self.source_schema}"."alembic_version" LIMIT 1')
        )
        row = result.first()
        if row is None:
            return None
        value = row[0] if not hasattr(row, "_mapping") else row._mapping.get("version_num")
        return _string(value)

    async def build_inventory(self) -> dict[str, Any]:
        revision = await self._source_revision()
        table_counts: dict[str, int] = {}
        column_inventory: dict[str, list[str]] = {}
        missing_columns: dict[str, list[str]] = {}
        for table in sorted(
            set(REQUIRED_COLUMNS)
            | {
                "advertising_campaign_registrations",
                "advertising_campaigns",
                "guest_purchases",
                "partner_applications",
                "payment_method_configs",
                "promocode_uses",
                "promocodes",
                "referral_earnings",
                "system_settings",
                "ticket_messages",
                "tickets",
            }
        ):
            if table not in self.tables:
                continue
            columns = await self._source_columns(table)
            column_inventory[table] = sorted(columns)
            result = await self.source.execute(
                text(f'SELECT count(*) AS count FROM "{self.source_schema}"."{table}"')
            )
            table_counts[table] = int(result.scalar() or 0)
        for table, expected in REQUIRED_COLUMNS.items():
            missing = sorted(expected - set(column_inventory.get(table, [])))
            if table not in self.tables:
                missing = sorted(expected)
            if missing:
                missing_columns[table] = missing
        supported = revision in SUPPORTED_REVISIONS and not missing_columns
        self.inventory = {
            "source": self.source_type,
            "schema": self.source_schema,
            "revision": revision,
            "supported_revisions": sorted(SUPPORTED_REVISIONS),
            "supported": supported,
            "table_counts": table_counts,
            "columns": column_inventory,
            "missing_required_columns": missing_columns,
        }
        if revision not in SUPPORTED_REVISIONS:
            self.summary["blockers"].append(
                f"Unsupported Bedolaga database revision: {revision or 'missing'}"
            )
        if missing_columns:
            self.summary["blockers"].append("Required Bedolaga columns are missing")
        await _artifact(self.inventory_output, self.inventory)
        return self.inventory

    async def prepare_tariffs(self) -> None:
        rows = await self._fetch_rows("tariffs", order_by="display_order, id")
        built = bedolaga_build_tariff_catalog(rows)
        self.generated_tariff_catalog = built["catalog"]
        self.tariff_map.update(built["tariff_map"])
        self.summary["warnings"].extend(built["warnings"])
        for row in rows:
            source_id = _to_int(row.get("id"))
            key = self.tariff_map.get(str(source_id)) if source_id is not None else None
            if source_id is not None and key:
                self.tariff_id_map[source_id] = key
                self.summary["tariffs"]["mapped"] += 1

    async def _mapped_user_id(self, source_user_id: Any) -> int | None:
        source_id = _to_int(source_user_id)
        if source_id is None:
            return None
        if source_id in self.user_map:
            return self.user_map[source_id]
        mapping = await self._get_mapping("user", source_id)
        target_id = _to_int(mapping.target_id) if mapping else None
        if target_id is not None:
            self.user_map[source_id] = target_id
        return target_id

    async def _identity_candidates(self, row: dict[str, Any]) -> set[int]:
        candidates: set[int] = set()
        telegram_id = _to_int(row.get("telegram_id"))
        if telegram_id is not None:
            result = await self.target.execute(
                select(User.user_id).where(User.telegram_id == telegram_id)
            )
            candidates.update(int(value) for value in result.scalars().all())
        email = _string(row.get("email"), 254)
        if email and _truthy(row.get("email_verified")):
            result = await self.target.execute(
                select(User.user_id).where(func.lower(User.email) == email.lower())
            )
            candidates.update(int(value) for value in result.scalars().all())
        panel_id = _string(row.get("remnawave_id") or row.get("remnawave_uuid"), 255)
        if panel_id:
            result = await self.target.execute(
                select(User.user_id).where(User.panel_user_uuid == panel_id)
            )
            candidates.update(int(value) for value in result.scalars().all())
        for provider, key in (
            ("google", "google_id"),
            ("yandex", "yandex_id"),
            ("discord", "discord_id"),
            ("vk", "vk_id"),
        ):
            subject = _string(row.get(key), 255)
            if not subject:
                continue
            result = await self.target.execute(
                select(UserExternalIdentity.user_id).where(
                    UserExternalIdentity.provider == provider,
                    UserExternalIdentity.subject == subject,
                )
            )
            candidates.update(int(value) for value in result.scalars().all())
        return candidates

    async def _import_user_identities(self, row: dict[str, Any], target_id: int) -> None:
        email = _string(row.get("email"), 254)
        verified_at = _as_utc(row.get("email_verified_at"))
        verified = _truthy(row.get("email_verified"))
        if email and verified:
            existing = await self.target.execute(
                select(UserEmailAddress.email_address_id).where(
                    func.lower(UserEmailAddress.email) == email.lower()
                )
            )
            if existing.scalar_one_or_none() is None:
                self.target.add(
                    UserEmailAddress(
                        user_id=target_id,
                        email=email,
                        source="bedolaga",
                        verified_at=verified_at or datetime.now(UTC),
                        is_primary=True,
                        is_notification=True,
                    )
                )
        display_name = (
            " ".join(
                value
                for value in (_string(row.get("first_name")), _string(row.get("last_name")))
                if value
            )
            or None
        )
        for provider, key in (
            ("google", "google_id"),
            ("yandex", "yandex_id"),
            ("discord", "discord_id"),
            ("vk", "vk_id"),
        ):
            subject = _string(row.get(key), 255)
            if not subject:
                continue
            existing = await self.target.execute(
                select(UserExternalIdentity.identity_id).where(
                    UserExternalIdentity.provider == provider,
                    UserExternalIdentity.subject == subject,
                )
            )
            if existing.scalar_one_or_none() is None:
                self.target.add(
                    UserExternalIdentity(
                        user_id=target_id,
                        provider=provider,
                        subject=subject,
                        email=email,
                        email_verified=verified,
                        display_name=display_name,
                        last_used_at=_as_utc(row.get("cabinet_last_login")),
                    )
                )

    async def import_users(self) -> None:
        async for row in self._iter_rows("users", order_by="id"):
            source_id = _to_int(row.get("id"))
            if source_id is None:
                self.summary["users"]["skipped"] += 1
                continue
            self.source_balance_by_user[source_id] = _to_int(row.get("balance_kopeks")) or 0
            source_panel_id = _string(
                row.get("remnawave_id") or row.get("remnawave_uuid"),
                255,
            )
            if source_panel_id:
                self.source_panel_by_user[source_id] = source_panel_id
            mapped = await self._get_mapping("user", source_id)
            if mapped:
                target_id = _to_int(mapped.target_id)
                if target_id is not None:
                    self.user_map[source_id] = target_id
                self.summary["users"]["existing"] += 1
                continue
            candidates = await self._identity_candidates(row)
            if len(candidates) > 1:
                conflict = {"source_user_id": source_id, "target_user_ids": sorted(candidates)}
                self.summary["identity_conflicts"].append(conflict)
                self.summary["users"]["conflict"] += 1
                continue
            telegram_id = _to_int(row.get("telegram_id"))
            target_id = next(iter(candidates), bedolaga_target_user_id(source_id, telegram_id))
            target = await self.target.get(User, target_id)
            if target is not None and not candidates:
                conflict = {"source_user_id": source_id, "target_user_ids": [target_id]}
                self.summary["identity_conflicts"].append(conflict)
                self.summary["users"]["conflict"] += 1
                continue
            if target is None:
                panel_id = row.get("remnawave_id") or row.get("remnawave_uuid")
                email = _string(row.get("email"), 254)
                if email and not _truthy(row.get("email_verified")):
                    email_owner = await self.target.execute(
                        select(User.user_id).where(func.lower(User.email) == email.lower())
                    )
                    if email_owner.scalar_one_or_none() is not None:
                        email = None
                        self.summary["users"]["unverified_email_preserved_elsewhere"] += 1
                referral_code = _string(row.get("referral_code"), 64)
                if referral_code:
                    referral_owner = await self.target.execute(
                        select(User.user_id).where(User.referral_code == referral_code)
                    )
                    if referral_owner.scalar_one_or_none() is not None:
                        referral_code = None
                        self.summary["users"]["referral_code_conflict"] += 1
                target = User(
                    user_id=target_id,
                    telegram_id=telegram_id,
                    username=_string(row.get("username"), 255),
                    email=email,
                    email_verified_at=_as_utc(row.get("email_verified_at"))
                    if _truthy(row.get("email_verified"))
                    else None,
                    notification_email=_string(row.get("email"), 254)
                    if _truthy(row.get("email_verified"))
                    else None,
                    first_name=_string(row.get("first_name"), 255),
                    last_name=_string(row.get("last_name"), 255),
                    language_code=_string(row.get("language"), 8) or "ru",
                    registration_date=_as_utc(row.get("created_at")) or datetime.now(UTC),
                    is_banned=_enum_text(row.get("status")) in {"blocked", "deleted"},
                    panel_user_uuid=_string(panel_id, 255),
                    referral_code=referral_code,
                    lifetime_used_traffic_bytes=_to_int(row.get("lifetime_used_traffic_bytes")),
                    lifetime_used_traffic_synced_at=_as_utc(row.get("updated_at")),
                )
                self.target.add(target)
                await self.target.flush()
                self.summary["users"]["created"] += 1
            elif self.on_conflict == "skip":
                self.summary["users"]["skipped"] += 1
                self.user_map[source_id] = target_id
                await self._upsert_mapping(
                    entity_type="user",
                    source_id=source_id,
                    target_table="users",
                    target_id=target_id,
                    metadata={"telegram": telegram_id is not None, "merge": "skipped"},
                )
                continue
            else:
                self._merge_existing_user_profile(
                    target,
                    username=row.get("username"),
                    first_name=_string(row.get("first_name"), 255),
                    last_name=_string(row.get("last_name"), 255),
                    language=_string(row.get("language"), 8),
                )
                if _truthy(row.get("email_verified")):
                    self._assign_if_allowed(target, "email", _string(row.get("email"), 254))
                    self._assign_if_allowed(
                        target,
                        "email_verified_at",
                        _as_utc(row.get("email_verified_at")) or datetime.now(UTC),
                    )
                self._assign_if_allowed(
                    target,
                    "panel_user_uuid",
                    _string(row.get("remnawave_id") or row.get("remnawave_uuid"), 255),
                )
                self.summary["users"]["merged"] += 1
            self.user_map[source_id] = target_id
            await self._import_user_identities(row, target_id)
            await self._upsert_mapping(
                entity_type="user",
                source_id=source_id,
                target_table="users",
                target_id=target_id,
                metadata={"telegram": telegram_id is not None, "email": bool(row.get("email"))},
            )

    async def import_referrals(self) -> None:
        async for row in self._iter_rows("users", order_by="id"):
            source_id = _to_int(row.get("id"))
            referrer_source_id = _to_int(row.get("referred_by_id"))
            target_id = await self._mapped_user_id(source_id)
            referrer_id = await self._mapped_user_id(referrer_source_id)
            if not target_id or not referrer_id or target_id == referrer_id:
                if referrer_source_id is not None:
                    self.summary["referrals"]["skipped"] += 1
                continue
            target = await self.target.get(User, target_id)
            if target is not None and (target.referred_by_id is None or self._can_overwrite()):
                target.referred_by_id = referrer_id
                self.summary["referrals"]["updated"] += 1
            await self._upsert_mapping(
                entity_type="referral",
                source_id=source_id,
                target_table="users",
                target_id=target_id,
                metadata={"referrer_user_id": referrer_id},
            )

    async def import_subscriptions(self) -> None:
        now = datetime.now(UTC)
        if not self.source_panel_by_user:
            async for user_row in self._iter_rows("users", order_by="id"):
                source_user_id = _to_int(user_row.get("id"))
                source_panel_id = _string(
                    user_row.get("remnawave_id") or user_row.get("remnawave_uuid"),
                    255,
                )
                if source_user_id is not None and source_panel_id:
                    self.source_panel_by_user[source_user_id] = source_panel_id
        async for row in self._iter_rows("subscriptions", order_by="id"):
            source_id = _to_int(row.get("id"))
            if source_id is None or await self._get_mapping("subscription", source_id):
                self.summary["subscriptions"]["existing"] += 1
                continue
            user_id = await self._mapped_user_id(row.get("user_id"))
            end_at = _as_utc(row.get("end_date"))
            if user_id is None or end_at is None:
                self.summary["subscriptions"]["skipped"] += 1
                continue
            start_at = _as_utc(row.get("start_date")) or _as_utc(row.get("created_at"))
            days = (
                max(0, math.ceil((end_at - start_at).total_seconds() / 86400)) if start_at else None
            )
            is_trial = _truthy(row.get("is_trial"))
            source_status = _enum_text(row.get("status"))
            source_user_id = _to_int(row.get("user_id"))
            panel_id = (
                row.get("remnawave_id")
                or row.get("remnawave_uuid")
                or self.source_panel_by_user.get(source_user_id or -1)
            )
            if panel_id is None:
                panel_id = f"bedolaga-unresolved:{source_id}"
                self.summary["subscriptions"]["unresolved_panel_identity"] += 1
                if source_status in {"active", "trial", "disabled"} and end_at > now:
                    self.summary["subscriptions"]["unresolved_active_panel_identity"] += 1
                    self.summary["blockers"].append(
                        f"Subscription {source_id} has no recoverable panel identity"
                    )
            tariff_id = _to_int(row.get("tariff_id"))
            tariff_key = self.tariff_id_map.get(tariff_id or -1)
            model = Subscription(
                user_id=user_id,
                panel_user_uuid=str(panel_id),
                panel_subscription_uuid=bedolaga_panel_subscription_uuid(row),
                start_date=start_at,
                end_date=end_at,
                duration_days=days,
                period_semantics="day" if days else None,
                is_active=source_status in {"active", "trial"} and end_at > now,
                status_from_panel="TRIAL" if is_trial else source_status.upper(),
                traffic_limit_bytes=int((_to_float(row.get("traffic_limit_gb")) or 0) * GIB),
                traffic_used_bytes=int((_to_float(row.get("traffic_used_gb")) or 0) * GIB),
                provider="trial" if is_trial else "bedolaga",
                auto_renew_enabled=_truthy(row.get("autopay_enabled")),
                tariff_key=tariff_key,
                tariff_binding_source="legacy_import" if tariff_key else None,
                tariff_bound_at=_as_utc(row.get("updated_at")) if tariff_key else None,
                tariff_binding_note=f"Bedolaga tariff {tariff_id}" if tariff_id else None,
                tier_baseline_bytes=int((_to_float(row.get("traffic_limit_gb")) or 0) * GIB),
                topup_balance_bytes=int((_to_float(row.get("purchased_traffic_gb")) or 0) * GIB),
                hwid_device_limit=max(1, _to_int(row.get("device_limit")) or 1),
                hwid_device_limit_is_override=True,
                tariff_managed_squad_uuids=_json_dumps(_json_list(row.get("connected_squads"))),
            )
            self.target.add(model)
            await self.target.flush()
            target_id = model.subscription_id or source_id
            await self._upsert_mapping(
                entity_type="subscription",
                source_id=source_id,
                target_table="subscriptions",
                target_id=target_id,
                metadata={
                    "source_status": source_status,
                    "is_trial": is_trial,
                    "tariff_key": tariff_key,
                },
            )
            if is_trial:
                user = await self.target.get(User, user_id)
                if user is not None and user.trial_eligibility_reset_at is None:
                    user.trial_eligibility_reset_at = start_at or datetime.now(UTC)
            self.summary["subscriptions"]["created"] += 1

    async def import_payments(self) -> None:
        async for row in self._iter_rows("transactions", order_by="id"):
            source_id = _to_int(row.get("id"))
            source_user_id = _to_int(row.get("user_id"))
            effect = bedolaga_ledger_effect(row.get("type"), row.get("amount_kopeks"))
            if source_user_id is not None and effect and _truthy(row.get("is_completed")):
                self.ledger_effect_by_user[source_user_id] += effect[1]
            if source_id is None or await self._get_mapping("payment", source_id):
                self.summary["payments"]["existing"] += 1
                continue
            user_id = await self._mapped_user_id(source_user_id)
            if user_id is None:
                self.summary["payments"]["skipped"] += 1
                continue
            transaction_type = _enum_text(row.get("type")) or "legacy"
            method = _enum_text(row.get("payment_method")) or "legacy"
            completed = _truthy(row.get("is_completed"))
            amount_minor = abs(_to_int(row.get("amount_kopeks")) or 0)
            model = Payment(
                user_id=user_id,
                provider=f"legacy_{method}"[:64],
                provider_payment_id=f"bedolaga:{source_id}",
                funding_source="user_balance"
                if transaction_type in {"subscription_payment", "gift_payment"}
                else "external",
                idempotence_key=f"bedolaga:transaction:{source_id}",
                amount=amount_minor / 100,
                currency="RUB",
                status=bedolaga_payment_status(completed),
                description=_string(row.get("description")),
                sale_mode=transaction_type,
                fulfillment_source="legacy_import" if completed else None,
                fulfilled_at=_as_utc(row.get("completed_at")) if completed else None,
                created_at=_as_utc(row.get("created_at")) or datetime.now(UTC),
            )
            self.target.add(model)
            await self.target.flush()
            payment_id = model.payment_id or source_id
            await self._upsert_mapping(
                entity_type="payment",
                source_id=source_id,
                target_table="payments",
                target_id=payment_id,
                metadata={"type": transaction_type, "method": method, "completed": completed},
            )
            if completed and effect:
                ledger = UserBalanceLedgerEntry(
                    user_id=user_id,
                    currency="RUB",
                    currency_scale=2,
                    amount_minor=effect[1],
                    kind=effect[0],
                    state="posted",
                    reference_type="legacy_payment",
                    reference_id=str(payment_id),
                    idempotency_key=f"bedolaga:transaction:{source_id}:balance",
                    reason=f"Bedolaga {transaction_type}",
                    metadata_json=_json_dumps({"source_transaction_id": source_id}),
                    created_at=_as_utc(row.get("completed_at")) or _as_utc(row.get("created_at")),
                    posted_at=_as_utc(row.get("completed_at")) or _as_utc(row.get("created_at")),
                )
                self.target.add(ledger)
                self.summary["balance_ledger"]["transactions"] += 1
            self.summary["payments"]["created"] += 1
        await self._import_balance_adjustments()

    async def _import_balance_adjustments(self) -> None:
        if not self.source_balance_by_user:
            async for row in self._iter_rows("users", order_by="id"):
                source_id = _to_int(row.get("id"))
                if source_id is not None:
                    self.source_balance_by_user[source_id] = _to_int(row.get("balance_kopeks")) or 0
        for source_id, source_balance in self.source_balance_by_user.items():
            target_id = await self._mapped_user_id(source_id)
            if target_id is None:
                continue
            adjustment = source_balance - self.ledger_effect_by_user.get(source_id, 0)
            if not adjustment:
                continue
            mapping = await self._get_mapping("balance_adjustment", source_id)
            if mapping:
                continue
            self.target.add(
                UserBalanceLedgerEntry(
                    user_id=target_id,
                    currency="RUB",
                    currency_scale=2,
                    amount_minor=adjustment,
                    kind="admin_adjustment",
                    state="posted",
                    reference_type="legacy_import",
                    reference_id=str(source_id),
                    idempotency_key=f"bedolaga:user:{source_id}:opening-balance",
                    actor_admin_id=self.created_by_admin_id or None,
                    reason="Bedolaga opening balance reconciliation",
                    metadata_json=_json_dumps({"source_user_id": source_id}),
                    created_at=datetime.now(UTC),
                    posted_at=datetime.now(UTC),
                )
            )
            await self._upsert_mapping(
                entity_type="balance_adjustment",
                source_id=source_id,
                target_table="user_balance_ledger_entries",
                target_id=f"bedolaga:user:{source_id}:opening-balance",
                metadata={"amount_minor": adjustment},
            )
            self.summary["balance_ledger"]["adjustments"] += 1

    async def import_promocodes(self) -> None:
        promo_targets: dict[int, int] = {}
        async for row in self._iter_rows("promocodes", order_by="id"):
            source_id = _to_int(row.get("id"))
            code = _string(row.get("code"), 128)
            promo_type = _enum_text(row.get("type"))
            if source_id is None or not code:
                continue
            mapping = await self._get_mapping("promocode", source_id)
            if mapping:
                target_id = _to_int(mapping.target_id)
                if target_id:
                    promo_targets[source_id] = target_id
                self.summary["promocodes"]["existing"] += 1
                continue
            if promo_type not in {"subscription_days", "discount", "balance_and_days"}:
                await self._upsert_mapping(
                    entity_type="promocode_archive",
                    source_id=source_id,
                    target_table="legacy_import_mappings",
                    target_id=source_id,
                    metadata={"type": promo_type, "reason": "unsupported_entitlement"},
                )
                self.summary["promocodes"]["archived"] += 1
                continue
            existing = await self.target.execute(select(PromoCode).where(PromoCode.code == code))
            model = existing.scalar_one_or_none()
            if model is None:
                discount = (
                    _to_float(row.get("balance_bonus_kopeks")) if promo_type == "discount" else None
                )
                model = PromoCode(
                    code=code,
                    bonus_days=max(0, _to_int(row.get("subscription_days")) or 0),
                    regular_traffic_gb=max(0, _to_float(row.get("traffic_gb")) or 0),
                    premium_traffic_gb=0,
                    discount_percent=min(100, max(0, discount or 0))
                    if discount is not None
                    else None,
                    bonus_requires_payment=_truthy(row.get("first_purchase_only")),
                    applies_to="subscription",
                    origin="legacy_bedolaga",
                    max_activations=max(1, _to_int(row.get("max_uses")) or 1),
                    current_activations=max(0, _to_int(row.get("current_uses")) or 0),
                    is_active=_truthy(row.get("is_active")),
                    created_by_admin_id=self.created_by_admin_id or None,
                    created_at=_as_utc(row.get("created_at")),
                    valid_until=_as_utc(row.get("valid_until")),
                )
                self.target.add(model)
                await self.target.flush()
                self.summary["promocodes"]["created"] += 1
            target_id = model.promo_code_id or source_id
            promo_targets[source_id] = target_id
            await self._upsert_mapping(
                entity_type="promocode",
                source_id=source_id,
                target_table="promo_codes",
                target_id=target_id,
                metadata={"type": promo_type},
            )
        async for row in self._iter_rows("promocode_uses", order_by="id"):
            source_id = _to_int(row.get("id"))
            promo_id = promo_targets.get(_to_int(row.get("promocode_id")) or -1)
            user_id = await self._mapped_user_id(row.get("user_id"))
            if source_id is None or promo_id is None or user_id is None:
                continue
            if await self._get_mapping("promocode_use", source_id):
                continue
            self.target.add(
                PromoCodeActivation(
                    promo_code_id=promo_id,
                    user_id=user_id,
                    activated_at=_as_utc(row.get("used_at")) or datetime.now(UTC),
                    effect_summary="Imported from Bedolaga",
                )
            )
            await self.target.flush()
            await self._upsert_mapping(
                entity_type="promocode_use",
                source_id=source_id,
                target_table="promo_code_activations",
                target_id=source_id,
            )

    async def import_gifts(self) -> None:
        async for row in self._iter_rows("guest_purchases", order_by="id"):
            if not _truthy(row.get("is_gift")):
                continue
            source_id = _to_int(row.get("id"))
            status = _enum_text(row.get("status"))
            if source_id is None or await self._get_mapping("gift", source_id):
                self.summary["gifts"]["existing"] += 1
                continue
            if status not in {"paid", "delivered"}:
                await self._upsert_mapping(
                    entity_type="gift_archive",
                    source_id=source_id,
                    target_table="legacy_import_mappings",
                    target_id=source_id,
                    metadata={"status": status},
                )
                self.summary["gifts"]["archived"] += 1
                continue
            purchaser_id = await self._mapped_user_id(row.get("buyer_user_id"))
            recipient_id = await self._mapped_user_id(row.get("user_id"))
            owner_id = purchaser_id or recipient_id
            if owner_id is None:
                self.summary["gifts"]["skipped"] += 1
                continue
            payment = Payment(
                user_id=owner_id,
                provider="legacy_bedolaga_gift",
                provider_payment_id=f"bedolaga:gift:{source_id}",
                funding_source="external",
                idempotence_key=f"bedolaga:gift:{source_id}",
                amount=abs(_to_int(row.get("amount_kopeks")) or 0) / 100,
                currency=_string(row.get("currency"), 16) or "RUB",
                status="succeeded",
                description="Imported Bedolaga gift",
                subscription_duration_days=max(0, _to_int(row.get("period_days")) or 0),
                period_semantics="day",
                sale_mode="gift",
                tariff_key=self.tariff_id_map.get(_to_int(row.get("tariff_id")) or -1),
                fulfillment_source="legacy_import",
                fulfilled_at=_as_utc(row.get("delivered_at")) or _as_utc(row.get("paid_at")),
                created_at=_as_utc(row.get("created_at")),
            )
            self.target.add(payment)
            await self.target.flush()
            payment_id = payment.payment_id or source_id
            token = (
                _string(row.get("token"), 64)
                or hashlib.sha256(f"bedolaga:{source_id}".encode()).hexdigest()
            )
            recipient_email = None
            if _enum_text(row.get("gift_recipient_type")) == "email":
                recipient_email = _string(row.get("gift_recipient_value"), 254)
            gift = SubscriptionGift(
                payment_id=payment_id,
                purchaser_id=purchaser_id,
                token=token,
                status="activated" if status == "delivered" else "ready",
                recipient_id=recipient_id,
                activated_at=_as_utc(row.get("delivered_at")) if status == "delivered" else None,
                bonus_days=max(0, _to_int(row.get("period_days")) or 0),
                recipient_email=recipient_email,
                delivery_status="delivered" if status == "delivered" else "not_requested",
                delivered_at=_as_utc(row.get("delivered_at")),
                created_at=_as_utc(row.get("created_at")),
            )
            self.target.add(gift)
            await self.target.flush()
            await self._upsert_mapping(
                entity_type="gift",
                source_id=source_id,
                target_table="subscription_gifts",
                target_id=gift.gift_id or source_id,
                metadata={"status": status},
            )
            self.summary["gifts"]["created"] += 1

    async def build_reconciliation(self) -> dict[str, Any]:
        source_counts = self.inventory.get("table_counts", {})
        source_balance_total = sum(self.source_balance_by_user.values())
        planned_balance_total = sum(self.ledger_effect_by_user.values()) + sum(
            source_balance - self.ledger_effect_by_user.get(source_id, 0)
            for source_id, source_balance in self.source_balance_by_user.items()
        )
        target_mapping_counts: dict[str, int] = {}
        balance_mismatches: list[dict[str, int]] = []
        if not self.dry_run:
            mapping_result = await self.target.execute(
                text(
                    """
                    SELECT entity_type, count(*) AS count
                    FROM legacy_import_mappings
                    WHERE source = 'bedolaga'
                    GROUP BY entity_type
                    ORDER BY entity_type
                    """
                )
            )
            target_mapping_counts = {str(row[0]): int(row[1]) for row in mapping_result.all()}
            balance_result = await self.target.execute(
                text(
                    """
                    SELECT mapping.source_id,
                           COALESCE(sum(ledger.amount_minor), 0) AS balance_minor
                    FROM legacy_import_mappings AS mapping
                    LEFT JOIN user_balance_ledger_entries AS ledger
                      ON ledger.user_id = CAST(mapping.target_id AS bigint)
                     AND ledger.currency = 'RUB'
                     AND ledger.state = 'posted'
                    WHERE mapping.source = 'bedolaga'
                      AND mapping.entity_type = 'user'
                    GROUP BY mapping.source_id
                    """
                )
            )
            target_balances = {int(row[0]): int(row[1]) for row in balance_result.all()}
            for source_id, source_balance in self.source_balance_by_user.items():
                target_balance = target_balances.get(source_id)
                if target_balance != source_balance:
                    balance_mismatches.append(
                        {
                            "source_user_id": source_id,
                            "source_minor": source_balance,
                            "target_minor": target_balance or 0,
                        }
                    )
            if balance_mismatches:
                self.summary["blockers"].append(
                    f"Balance reconciliation failed for {len(balance_mismatches)} users"
                )
        self.reconciliation = {
            "source": self.source_type,
            "revision": self.inventory.get("revision"),
            "dry_run": self.dry_run,
            "source_counts": source_counts,
            "target_mapping_counts": target_mapping_counts,
            "import_summary": self._plain_summary(),
            "invariants": {
                "source_and_target_are_distinct": True,
                "source_revision_supported": bool(self.inventory.get("supported")),
                "balance_total_source_minor": source_balance_total,
                "balance_total_planned_minor": planned_balance_total,
                "balance_total_matches": source_balance_total == planned_balance_total,
                "balance_user_mismatches": len(balance_mismatches),
                "identity_conflicts": len(self.summary["identity_conflicts"]),
                "unresolved_panel_subscriptions": self.summary["subscriptions"].get(
                    "unresolved_panel_identity", 0
                ),
                "unresolved_active_panel_subscriptions": self.summary["subscriptions"].get(
                    "unresolved_active_panel_identity", 0
                ),
            },
            "balance_mismatch_sample": balance_mismatches[:50],
            "blockers": list(self.summary["blockers"]),
            "warnings": list(self.summary["warnings"]),
        }
        await _artifact(self.reconciliation_output, self.reconciliation)
        return self.reconciliation

    async def run(self) -> dict[str, Any]:
        self.tables = await self._source_tables()
        await self.build_inventory()
        if not self.inventory.get("supported") and not self.dry_run:
            raise RuntimeError("Bedolaga source inventory is incompatible; apply is blocked")
        await self.prepare_tariffs()
        if self._should_run("users"):
            await self.import_users()
        if self._should_run("referrals"):
            await self.import_referrals()
        if self._should_run("subscriptions"):
            await self.import_subscriptions()
        if self._should_run("payments"):
            await self.import_payments()
        if self._should_run("gifts"):
            await self.import_gifts()
        if self._should_run("promocodes"):
            await self.import_promocodes()
        if self._should_run("support"):
            await self.import_support()
        if self._should_run("advertising"):
            await self.import_advertising()
        if self._should_run("partners"):
            await self.import_partners()
        if self._should_run("settings"):
            await self.import_settings()
        await self.build_reconciliation()
        if self.summary["blockers"] and not self.dry_run:
            raise RuntimeError("Bedolaga reconciliation has blockers; apply was rolled back")
        return self._plain_summary()
