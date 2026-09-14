"""Subscription, payment and activation-code import."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.dal import user_panel_squad_override_dal
from db.models import (
    Payment,
    PromoCode,
    PromoCodeActivation,
    Subscription,
)

from .common import (
    SOURCE,
    _as_mapping,
    _as_utc,
    _json_dumps,
    _jsonish,
    _listish,
    _qtable,
    _to_int,
)
from .remnashop_data import (
    _extract_panel_subscription_uuid,
    _provider_value,
    remnashop_days_from_plan_snapshot,
    remnashop_months_from_plan_snapshot,
    remnashop_plan_type,
    remnashop_pricing_amount,
    remnashop_pricing_currency,
    remnashop_purchased_gb,
    remnashop_purchased_hwid_devices,
    remnashop_sale_mode,
    remnashop_subscription_provider,
    remnashop_tariff_key,
    remnashop_traffic_gb_to_bytes,
    remnashop_transaction_status,
)
from .remnashop_users import _RemnashopUsersSection

logger = logging.getLogger(__name__)


class _RemnashopSalesSection(_RemnashopUsersSection):
    async def _import_subscription_squad_overrides(
        self,
        *,
        user_id: int,
        panel_user_uuid: str,
        row: dict[str, Any],
        managed_internal: list[str],
        plan_snapshot: dict[str, Any],
    ) -> None:
        actual_internal = [str(value).strip() for value in _listish(row.get("internal_squads"))]
        actual_internal = [value for value in actual_internal if value]
        last_seen_at = _as_utc(row.get("updated_at")) or _as_utc(row.get("created_at"))
        for squad_uuid in sorted(set(actual_internal) - set(managed_internal)):
            await user_panel_squad_override_dal.upsert_internal_override(
                self.target,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
                squad_uuid=squad_uuid,
                source=user_panel_squad_override_dal.OVERRIDE_SOURCE_PANEL,
                last_seen_at=last_seen_at,
                note="Imported from Remnashop subscription state",
            )
            self.summary["squad_overrides"]["internal"] += 1

        actual_external = str(row.get("external_squad") or "").strip() or None
        planned_external = str(plan_snapshot.get("external_squad") or "").strip() or None
        if actual_external == planned_external:
            return
        if actual_external:
            await user_panel_squad_override_dal.set_external_override(
                self.target,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
                mode=user_panel_squad_override_dal.OVERRIDE_MODE_SET,
                squad_uuid=actual_external,
                source=user_panel_squad_override_dal.OVERRIDE_SOURCE_PANEL,
                last_seen_at=last_seen_at,
            )
            self.summary["squad_overrides"]["external_set"] += 1
        elif planned_external:
            await user_panel_squad_override_dal.set_external_override(
                self.target,
                user_id=user_id,
                panel_user_uuid=panel_user_uuid,
                mode=user_panel_squad_override_dal.OVERRIDE_MODE_CLEARED,
                source=user_panel_squad_override_dal.OVERRIDE_SOURCE_PANEL,
                last_seen_at=last_seen_at,
            )
            self.summary["squad_overrides"]["external_cleared"] += 1

    async def import_subscriptions(self) -> None:
        rows = await self._fetch_rows("subscriptions", order_by="id")
        now = datetime.now(UTC)
        for row in rows:
            user = await self._target_user_for_source_row(row)
            if not user:
                self.summary["subscriptions"]["skipped"] += 1
                continue

            panel_user_uuid = str(row.get("user_remna_id") or user.panel_user_uuid or "").strip()
            if not panel_user_uuid:
                self.summary["subscriptions"]["skipped"] += 1
                continue
            if not user.panel_user_uuid or self._can_overwrite():
                user.panel_user_uuid = panel_user_uuid

            source_id = row.get("id")
            mapping = await self._get_mapping("subscription", source_id)
            existing: Subscription | None = None
            if mapping and str(mapping.target_id).isdigit():
                existing = await self.target.get(Subscription, int(mapping.target_id))

            panel_sub_uuid = _extract_panel_subscription_uuid(row.get("url"), panel_user_uuid)
            if not existing and panel_sub_uuid:
                existing = (
                    await self.target.execute(
                        select(Subscription).where(
                            Subscription.panel_subscription_uuid == panel_sub_uuid
                        )
                    )
                ).scalar_one_or_none()

            status = str(row.get("status") or "UNKNOWN").strip().upper()
            expire_at = _as_utc(row.get("expire_at")) or now
            created_at = _as_utc(row.get("created_at")) or now
            plan_snapshot = _jsonish(row.get("plan_snapshot"))
            plan_type = remnashop_plan_type(plan_snapshot)
            traffic_limit_bytes = remnashop_traffic_gb_to_bytes(row.get("traffic_limit"))
            actual_internal = [str(value).strip() for value in _listish(row.get("internal_squads"))]
            actual_internal = [value for value in actual_internal if value]
            managed_internal = [
                str(value).strip() for value in _listish(plan_snapshot.get("internal_squads"))
            ]
            managed_internal = [value for value in managed_internal if value]
            if not managed_internal:
                managed_internal = list(actual_internal)
            actual_device_limit = _to_int(row.get("device_limit"))
            planned_device_limit = _to_int(plan_snapshot.get("device_limit"))
            payload = {
                "user_id": int(user.user_id),
                "panel_user_uuid": panel_user_uuid,
                "panel_subscription_uuid": panel_sub_uuid,
                "start_date": created_at,
                "end_date": expire_at,
                "duration_days": remnashop_days_from_plan_snapshot(plan_snapshot)
                if not row.get("is_trial") and plan_type != "TRAFFIC"
                else None,
                "period_semantics": "fixed_days"
                if not row.get("is_trial") and plan_type != "TRAFFIC"
                else None,
                "duration_months": remnashop_months_from_plan_snapshot(
                    plan_snapshot,
                    created_at=created_at,
                    expire_at=expire_at,
                ),
                "is_active": status in {"ACTIVE", "LIMITED"} and expire_at > now,
                "status_from_panel": status,
                "traffic_limit_bytes": traffic_limit_bytes,
                "provider": remnashop_subscription_provider(row.get("is_trial")),
                "skip_notifications": True,
                "auto_renew_enabled": False,
                "tariff_key": remnashop_tariff_key(plan_snapshot, self.tariff_map),
                "tier_baseline_bytes": 0 if plan_type == "TRAFFIC" else traffic_limit_bytes,
                "topup_balance_bytes": traffic_limit_bytes if plan_type == "TRAFFIC" else 0,
                "period_start_at": None if plan_type == "TRAFFIC" else created_at,
                "hwid_device_limit": actual_device_limit,
                "hwid_device_limit_is_override": bool(
                    actual_device_limit is not None
                    and planned_device_limit is not None
                    and actual_device_limit != planned_device_limit
                ),
                "tariff_managed_squad_uuids": _json_dumps(managed_internal),
            }
            metadata = {
                "source": SOURCE,
                "source_subscription_id": source_id,
                "traffic_limit_strategy": str(row.get("traffic_limit_strategy") or ""),
                "tag": row.get("tag"),
                "internal_squads": [str(item) for item in _listish(row.get("internal_squads"))],
                "external_squad": str(row.get("external_squad") or "") or None,
                "url": row.get("url"),
                "plan_snapshot": plan_snapshot,
            }

            if existing:
                if self.on_conflict == "skip":
                    self.summary["subscriptions"]["skipped"] += 1
                else:
                    for key, value in payload.items():
                        self._assign_if_allowed(existing, key, value)
                    self.summary["subscriptions"]["updated"] += 1
                target_subscription_id = existing.subscription_id
            else:
                subscription = Subscription(**payload)
                self.target.add(subscription)
                await self.target.flush()
                target_subscription_id = subscription.subscription_id
                self.summary["subscriptions"]["created"] += 1

            await self._upsert_mapping(
                entity_type="subscription",
                source_id=source_id,
                target_table="subscriptions",
                target_id=target_subscription_id,
                metadata=metadata,
            )
            await self._import_subscription_squad_overrides(
                user_id=int(user.user_id),
                panel_user_uuid=panel_user_uuid,
                row=row,
                managed_internal=managed_internal,
                plan_snapshot=plan_snapshot,
            )

        await self.target.flush()

    async def import_payments(self) -> None:
        rows = await self._fetch_rows("transactions", order_by="id")
        for row in rows:
            user = await self._target_user_for_source_row(row)
            if not user:
                self.summary["payments"]["skipped"] += 1
                continue

            provider = _provider_value(row.get("gateway_type"))
            provider_payment_id = f"{SOURCE}:{row.get('payment_id') or row.get('id')}"
            existing = (
                await self.target.execute(
                    select(Payment).where(
                        Payment.provider == provider,
                        Payment.provider_payment_id == provider_payment_id,
                    )
                )
            ).scalar_one_or_none()

            plan_snapshot = _jsonish(row.get("plan_snapshot"))
            created_at = _as_utc(row.get("created_at"))
            sale_mode = remnashop_sale_mode(row.get("purchase_type"), plan_snapshot)
            payload = {
                "user_id": int(user.user_id),
                "provider_payment_id": provider_payment_id,
                "provider": provider,
                "amount": remnashop_pricing_amount(row.get("pricing")),
                "currency": remnashop_pricing_currency(row.get("pricing"), row.get("currency")),
                "status": remnashop_transaction_status(row.get("status"), provider),
                "description": self._payment_description(row),
                "subscription_duration_days": remnashop_days_from_plan_snapshot(plan_snapshot)
                if sale_mode == "subscription"
                else None,
                "period_semantics": "fixed_days" if sale_mode == "subscription" else None,
                "subscription_duration_months": remnashop_months_from_plan_snapshot(
                    plan_snapshot,
                    created_at=row.get("created_at"),
                    expire_at=None,
                )
                if sale_mode == "subscription"
                else None,
                "sale_mode": sale_mode,
                "tariff_key": remnashop_tariff_key(plan_snapshot, self.tariff_map),
                "purchased_gb": remnashop_purchased_gb(plan_snapshot),
                "purchased_hwid_devices": remnashop_purchased_hwid_devices(plan_snapshot),
                "created_at": created_at,
            }
            payload = {key: value for key, value in payload.items() if value is not None}

            if existing:
                if self.on_conflict == "skip":
                    self.summary["payments"]["skipped"] += 1
                else:
                    for key, value in payload.items():
                        self._assign_if_allowed(existing, key, value)
                    self.summary["payments"]["updated"] += 1
                target_payment_id = existing.payment_id
            else:
                payment = Payment(**payload)
                self.target.add(payment)
                await self.target.flush()
                target_payment_id = payment.payment_id
                self.summary["payments"]["created"] += 1

            await self._upsert_mapping(
                entity_type="payment",
                source_id=row.get("payment_id") or row.get("id"),
                target_table="payments",
                target_id=target_payment_id,
                metadata={
                    "source_transaction_id": row.get("id"),
                    "is_test": row.get("is_test"),
                    "purchase_type": str(row.get("purchase_type") or ""),
                    "gateway_type": str(row.get("gateway_type") or ""),
                    "plan_snapshot": plan_snapshot,
                },
            )

        await self.target.flush()

    def _payment_description(self, row: dict[str, Any]) -> str:
        snapshot = _jsonish(row.get("plan_snapshot"))
        plan_name = str(snapshot.get("name") or snapshot.get("tag") or "").strip()
        purchase_type = str(row.get("purchase_type") or "").strip().upper()
        if plan_name:
            return f"Remnashop import: {purchase_type} {plan_name}".strip()
        return f"Remnashop import: {purchase_type}".strip()

    async def import_promocodes(self) -> None:
        if "promocodes" not in self.tables:
            self.summary["promocodes"]["missing_source_table"] += 1
            return

        activation_rows_by_code = await self._source_promocode_activation_rows()
        rows = await self._fetch_rows("promocodes", order_by="id")
        for row in rows:
            code = str(row.get("code") or "").strip()
            if not code:
                self.summary["promocodes"]["skipped"] += 1
                continue

            effects = self._promo_effects(row)
            if effects is None:
                self.summary["promocodes"]["unsupported_reward"] += 1
                continue

            existing = (
                await self.target.execute(select(PromoCode).where(PromoCode.code == code))
            ).scalar_one_or_none()
            activations = activation_rows_by_code.get(code, [])
            valid_until = _as_utc(row.get("expires_at"))
            lifetime_days = _to_int(row.get("lifetime"))
            if valid_until is None and lifetime_days and _as_utc(row.get("created_at")):
                valid_until = _as_utc(row.get("created_at"))
                if valid_until:
                    valid_until = valid_until + timedelta(days=lifetime_days)

            payload = {
                "code": code,
                **effects,
                "applies_to": "subscription",
                "origin": "legacy_remnashop",
                "max_activations": _to_int(row.get("max_activations")) or 1_000_000,
                "current_activations": len(activations),
                "is_active": bool(row.get("is_active")),
                "created_by_admin_id": self.created_by_admin_id,
                "created_at": _as_utc(row.get("created_at")),
                "valid_until": valid_until,
            }
            payload = {key: value for key, value in payload.items() if value is not None}

            if existing:
                if self.on_conflict == "skip":
                    self.summary["promocodes"]["skipped"] += 1
                else:
                    for key, value in payload.items():
                        self._assign_if_allowed(existing, key, value)
                    self.summary["promocodes"]["updated"] += 1
                promo = existing
            else:
                promo = PromoCode(**payload)
                self.target.add(promo)
                await self.target.flush()
                self.summary["promocodes"]["created"] += 1

            await self._upsert_mapping(
                entity_type="promocode",
                source_id=row.get("id") or code,
                target_table="promo_codes",
                target_id=promo.promo_code_id,
                metadata={
                    "reward_type": str(row.get("reward_type") or ""),
                    "reward": row.get("reward"),
                    "plan": _jsonish(row.get("plan") or row.get("plan_snapshot")),
                    "expires_at": row.get("expires_at"),
                    "lifetime": row.get("lifetime"),
                },
            )
            await self._import_promocode_activations(promo, activations)

        await self.target.flush()

    async def _source_promocode_activation_rows(self) -> dict[str, list[dict[str, Any]]]:
        if "promocode_activations" not in self.tables:
            return {}
        result = await self.source.execute(
            text(
                f"""
                SELECT a.*, p.code
                FROM {_qtable(self.source_schema, "promocode_activations")} a
                JOIN {_qtable(self.source_schema, "promocodes")} p
                  ON p.id = a.promocode_id
                ORDER BY a.id
                """
            )
        )
        by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in result.mappings().all():
            mapping = _as_mapping(row)
            code = str(mapping.get("code") or "").strip()
            if code:
                by_code[code].append(mapping)
        return by_code

    def _promo_effects(self, row: dict[str, Any]) -> dict[str, Any] | None:
        reward_type = str(row.get("reward_type") or "").strip().upper()
        if reward_type == "DURATION":
            days = _to_int(row.get("reward"))
            return {"bonus_days": days} if days and days > 0 else None
        if reward_type == "TRAFFIC":
            traffic_gb = row.get("reward")
            try:
                normalized_traffic = float(str(traffic_gb))
            except (TypeError, ValueError):
                return None
            return (
                {"bonus_days": 0, "regular_traffic_gb": normalized_traffic}
                if normalized_traffic > 0
                else None
            )
        if reward_type == "SUBSCRIPTION":
            plan = _jsonish(row.get("plan") or row.get("plan_snapshot"))
            days = (
                _to_int(plan.get("duration_days"))
                or _to_int(plan.get("days"))
                or _to_int(row.get("reward"))
            )
            return {"bonus_days": days} if days and days > 0 else None
        return None

    def _promo_bonus_days(self, row: dict[str, Any]) -> int | None:
        effects = self._promo_effects(row)
        return _to_int(effects.get("bonus_days")) if effects else None

    async def _import_promocode_activations(
        self,
        promo: PromoCode,
        activations: Iterable[dict[str, Any]],
    ) -> None:
        for activation in activations:
            source_id = activation.get("id") or (
                f"{activation.get('promocode_id')}:{activation.get('user_id')}"
            )
            if await self._get_mapping("promocode_activation", source_id):
                self.summary["promocodes"]["activation_existing"] += 1
                continue
            user = await self._target_user_for_source_row(activation)
            if not user:
                self.summary["promocodes"]["activation_skipped"] += 1
                continue
            stmt = (
                pg_insert(PromoCodeActivation)
                .values(
                    promo_code_id=promo.promo_code_id,
                    user_id=user.user_id,
                    activated_at=_as_utc(activation.get("activated_at")) or datetime.now(UTC),
                    effect_summary="Imported from Remnashop",
                    bonus_days=promo.bonus_days,
                    regular_traffic_gb=promo.regular_traffic_gb,
                    applies_to=promo.applies_to,
                    granted_days=promo.bonus_days or None,
                    granted_gb=float(promo.regular_traffic_gb or 0) or None,
                    granted_regular_traffic_gb=promo.regular_traffic_gb,
                    is_manual_override=False,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        PromoCodeActivation.promo_code_id,
                        PromoCodeActivation.user_id,
                    ],
                    index_where=PromoCodeActivation.is_manual_override.is_(False),
                )
            )
            await self.target.execute(stmt)
            await self._upsert_mapping(
                entity_type="promocode_activation",
                source_id=source_id,
                target_table="promo_code_activations",
                target_id=f"{promo.promo_code_id}:{user.user_id}",
            )
            self.summary["promocodes"]["activation_imported"] += 1
