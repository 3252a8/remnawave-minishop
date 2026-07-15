import logging
import math
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.traffic_reset import traffic_accounting_period_start, traffic_period_starts_match
from config.tariffs_config import (
    Tariff,
    TariffsConfig,
    default_currency_key_for_settings,
)
from config.traffic_strategy import normalize_traffic_limit_strategy
from db.dal import tariff_dal
from db.models import Subscription

from ._typing import SubscriptionServiceMixinContract

logger = logging.getLogger(__name__)


class TariffMixin(SubscriptionServiceMixinContract):
    @staticmethod
    def gb_to_bytes(gb: float) -> int:
        return int(float(gb) * (1024**3))

    @staticmethod
    def _far_future() -> datetime:
        return datetime(2099, 1, 1, tzinfo=UTC)

    def _tariffs_config(self) -> TariffsConfig | None:
        config = getattr(self.settings, "tariffs_config", None)
        return config if isinstance(config, TariffsConfig) else None

    def _default_tariff(self) -> Tariff | None:
        config = self._tariffs_config()
        return config.default if config else None

    def _resolve_tariff(
        self, tariff_key: str | None, billing_model: str | None = None
    ) -> Tariff | None:
        config = self._tariffs_config()
        if not config:
            return None
        tariff = config.require(tariff_key or config.default_tariff)
        if billing_model and tariff.billing_model != billing_model:
            raise ValueError(
                f"Tariff {tariff.key} is {tariff.billing_model}, expected {billing_model}"
            )
        return tariff

    def _subscription_billing_model(self, sub: Any | None) -> str | None:
        if sub is None:
            return None
        tariff_key = str(getattr(sub, "tariff_key", "") or "").strip()
        if not tariff_key:
            return None
        try:
            tariff = self._resolve_tariff(tariff_key)
        except Exception:
            logger.debug("Unable to resolve tariff %r for subscription state", tariff_key)
            return None
        return tariff.billing_model if tariff else None

    @staticmethod
    def _nonnegative_bytes(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    def _remaining_traffic_bytes(self, limit_bytes: Any, used_bytes: Any) -> int:
        limit = self._nonnegative_bytes(limit_bytes)
        if limit <= 0:
            return 0
        return max(0, limit - self._nonnegative_bytes(used_bytes))

    def _traffic_package_carryover_bytes(
        self,
        sub: Any | None,
        *,
        limit_bytes: Any,
        used_bytes: Any,
    ) -> int:
        if sub is None:
            return 0
        remaining = self._remaining_traffic_bytes(limit_bytes, used_bytes)
        if self._subscription_billing_model(sub) == "traffic":
            return remaining
        paid_topup_balance = self._nonnegative_bytes(getattr(sub, "topup_balance_bytes", 0))
        if paid_topup_balance <= 0:
            return 0
        return min(paid_topup_balance, remaining)

    def _traffic_limit_for_balance(
        self,
        *,
        used_bytes: Any,
        balance_bytes: Any,
        unlimited_override: bool = False,
    ) -> int:
        if unlimited_override:
            return 0
        return self._nonnegative_bytes(used_bytes) + self._nonnegative_bytes(balance_bytes)

    def _panel_squads_for_tariff(
        self,
        tariff: Tariff | None,
        *,
        include_premium: bool = True,
    ) -> list[str] | None:
        if tariff:
            squads = list(tariff.squad_uuids or [])
            if include_premium:
                squads.extend(tariff.premium_squad_uuids or [])
            return list(dict.fromkeys(squads))
        return list(self.settings.parsed_user_squad_uuids or [])

    def _catalog_premium_squad_uuid_set(self) -> set[str]:
        config = self._tariffs_config()
        if not config:
            return set()
        premium_squads: set[str] = set()
        for tariff in getattr(config, "tariffs", []) or []:
            premium_squads.update(str(uuid) for uuid in (tariff.premium_squad_uuids or []))
        return premium_squads

    def _trial_panel_squad_uuids(self) -> list[str]:
        squads = self.settings.parsed_trial_squad_uuids
        if not squads:
            squads = self.settings.parsed_user_squad_uuids or []
        premium_squads = set(self._trial_premium_squad_uuids())
        premium_squads.update(self._catalog_premium_squad_uuid_set())
        return list(
            dict.fromkeys(
                str(uuid)
                for uuid in squads
                if str(uuid or "").strip() and str(uuid) not in premium_squads
            )
        )

    def _trial_all_panel_squad_uuids(self) -> list[str]:
        squads = [*self._trial_panel_squad_uuids(), *self._trial_premium_squad_uuids()]
        return list(dict.fromkeys(str(uuid) for uuid in squads if str(uuid or "").strip()))

    def _trial_premium_squad_uuids(self) -> list[str]:
        squads = self.settings.parsed_trial_premium_squad_uuids or []
        return list(dict.fromkeys(str(uuid) for uuid in squads if str(uuid or "").strip()))

    def _trial_premium_baseline_bytes(self) -> int:
        if not self._trial_premium_squad_uuids():
            return 0
        return int(self.settings.trial_premium_traffic_limit_bytes or 0)

    def _traffic_limit_for_period_tariff(
        self,
        tariff: Tariff | None,
        topup_balance_bytes: int = 0,
        regular_bonus_bytes: int = 0,
        regular_unlimited_override: bool = False,
        traffic_used_bytes: int = 0,
    ) -> int:
        if tariff:
            baseline = int(tariff.monthly_bytes or 0)
        else:
            baseline = int(self.settings.user_traffic_limit_bytes)
        return self._compute_main_traffic_limit_bytes(
            tier_baseline_bytes=baseline,
            topup_balance_bytes=topup_balance_bytes,
            regular_bonus_bytes=regular_bonus_bytes,
            regular_unlimited_override=regular_unlimited_override,
            traffic_used_bytes=traffic_used_bytes,
        )

    def _premium_limit_for_tariff(self, tariff: Tariff | None, topup_balance_bytes: int = 0) -> int:
        if not tariff:
            return 0
        return int(tariff.premium_monthly_bytes + max(0, topup_balance_bytes))

    def _period_tariff_traffic_strategy(self, tariff: Tariff | None = None) -> str:
        configured_strategy = getattr(tariff, "traffic_limit_strategy", None)
        return normalize_traffic_limit_strategy(
            configured_strategy or getattr(self.settings, "USER_TRAFFIC_STRATEGY", "MONTH"),
            default="MONTH",
        )

    def _tariff_for_subscription(self, sub: Any | None) -> Tariff | None:
        tariff_key = str(getattr(sub, "tariff_key", "") or "").strip()
        if not tariff_key:
            return None
        try:
            return self._resolve_tariff(tariff_key)
        except Exception:
            logger.debug("Unable to resolve tariff %r for traffic strategy", tariff_key)
            return None

    def _premium_traffic_strategy_for_subscription(self, sub: Any | None) -> str:
        provider = str(getattr(sub, "provider", "") or "").strip().lower()
        status = str(getattr(sub, "status_from_panel", "") or "").strip().upper()
        if provider == "trial" or status == "TRIAL":
            return normalize_traffic_limit_strategy(
                getattr(self.settings, "TRIAL_TRAFFIC_STRATEGY", "NO_RESET"),
                default="NO_RESET",
            )
        return self._period_tariff_traffic_strategy(self._tariff_for_subscription(sub))

    def _premium_accounting_period_start(
        self,
        sub: Any,
        now: datetime,
        *,
        panel_user_data: dict[str, Any] | None = None,
    ) -> datetime:
        return traffic_accounting_period_start(
            self._premium_traffic_strategy_for_subscription(sub),
            now,
            subscription_start_at=self._aware_utc(getattr(sub, "start_date", None)),
            previous_period_start_at=self._aware_utc(getattr(sub, "premium_period_start_at", None)),
            panel_user_data=panel_user_data,
        )

    def _same_premium_accounting_period(
        self,
        sub: Any,
        premium_period_start: datetime,
        now: datetime,
    ) -> bool:
        current_period_start = self._aware_utc(getattr(sub, "premium_period_start_at", None))
        if current_period_start is None:
            return False
        strategy = self._premium_traffic_strategy_for_subscription(sub)
        if traffic_period_starts_match(current_period_start, premium_period_start, strategy):
            return True
        no_reset_anchor = self._aware_utc(getattr(sub, "start_date", None))
        return bool(
            strategy == "NO_RESET" and no_reset_anchor is not None and no_reset_anchor <= now
        )

    @staticmethod
    def _premium_effective_limit_bytes(
        premium_baseline_bytes: int,
        premium_topup_balance_bytes: int = 0,
        premium_topup_used_bytes: int = 0,
        premium_bonus_bytes: int = 0,
    ) -> int:
        return (
            int(premium_baseline_bytes or 0)
            + max(0, int(premium_topup_balance_bytes or 0))
            + max(0, int(premium_topup_used_bytes or 0))
            + max(0, int(premium_bonus_bytes or 0))
        )

    def _compute_main_traffic_limit_bytes(
        self,
        *,
        tier_baseline_bytes: int,
        topup_balance_bytes: int,
        regular_bonus_bytes: int,
        regular_unlimited_override: bool,
        traffic_used_bytes: int,
    ) -> int:
        """Numeric cap sent to the panel; Remnawave treats ``0`` as unlimited."""
        floor = (
            int(tier_baseline_bytes or 0)
            + max(0, int(topup_balance_bytes or 0))
            + max(0, int(regular_bonus_bytes or 0))
        )
        if regular_unlimited_override:
            return 0
        return floor

    async def premium_access_for_tariff(self, tariff: Tariff | None) -> dict[str, Any]:
        if not tariff or not tariff.premium_squad_uuids:
            return {"squad_uuids": [], "squad_labels": [], "node_labels": []}

        cache_key = tuple(sorted(str(uuid) for uuid in tariff.premium_squad_uuids))
        now_ts = datetime.now(UTC).timestamp()
        cached = self._premium_access_cache.get(cache_key)
        if cached and now_ts - float(cached.get("ts", 0)) < 600:
            return {
                "squad_uuids": list(cached.get("squad_uuids") or []),
                "squad_labels": list(cached.get("squad_labels") or []),
                "node_labels": list(cached.get("node_labels") or []),
            }

        def _extract_inbound_uuids(squad_obj: dict[str, Any]) -> list[str]:
            collected: list[str] = []
            for field in ("inbounds", "internalInbounds", "configProfileInbounds"):
                value = squad_obj.get(field)
                if not isinstance(value, list):
                    continue
                for inbound in value:
                    if isinstance(inbound, dict):
                        ib_uuid = str(
                            inbound.get("uuid")
                            or inbound.get("inboundUuid")
                            or inbound.get("id")
                            or ""
                        )
                    else:
                        ib_uuid = str(inbound or "")
                    if ib_uuid:
                        collected.append(ib_uuid)
            return collected

        squad_name_map: dict[str, str] = {}
        squad_inbound_map: dict[str, list[str]] = {}
        try:
            squads = await self.panel_service.get_internal_squads() or []
            for squad in squads:
                if not isinstance(squad, dict):
                    continue
                squad_uuid = str(squad.get("uuid") or squad.get("id") or "")
                if not squad_uuid:
                    continue
                squad_name_map[squad_uuid] = str(
                    squad.get("name") or squad.get("title") or squad_uuid
                )
                squad_inbound_map[squad_uuid] = _extract_inbound_uuids(squad)
        except Exception:
            logger.debug("Failed to load internal squad names for premium display", exc_info=True)

        for squad_uuid in tariff.premium_squad_uuids:
            squad_uuid_str = str(squad_uuid)
            if squad_inbound_map.get(squad_uuid_str):
                continue
            try:
                detail = await self.panel_service.get_internal_squad(squad_uuid_str)
            except Exception:
                logger.debug(
                    "Failed to load internal squad detail for %s", squad_uuid_str, exc_info=True
                )
                detail = None
            if isinstance(detail, dict):
                squad_inbound_map[squad_uuid_str] = _extract_inbound_uuids(detail)
                if squad_uuid_str not in squad_name_map:
                    squad_name_map[squad_uuid_str] = str(
                        detail.get("name") or detail.get("title") or squad_uuid_str
                    )

        def _host_is_user_visible(host: dict[str, Any]) -> bool:
            return not bool(
                host.get("isHidden")
                or host.get("is_hidden")
                or host.get("hidden")
                or host.get("isDisabled")
                or host.get("is_disabled")
                or host.get("disabled")
            )

        hosts_by_inbound: dict[str, list[dict[str, Any]]] = {}
        try:
            hosts = await self.panel_service.get_hosts() or []
            for host in hosts:
                if not isinstance(host, dict):
                    continue
                if not _host_is_user_visible(host):
                    continue
                inbound_raw = host.get("inbound")
                inbound_field: dict[str, Any] = inbound_raw if isinstance(inbound_raw, dict) else {}
                inbound_uuid = (
                    host.get("inboundUuid")
                    or host.get("inbound_uuid")
                    or host.get("configProfileInboundUuid")
                    or inbound_field.get("configProfileInboundUuid")
                    or inbound_field.get("inboundUuid")
                    or inbound_field.get("uuid")
                    or ""
                )
                inbound_uuid = str(inbound_uuid)
                if not inbound_uuid:
                    continue
                hosts_by_inbound.setdefault(inbound_uuid, []).append(host)
            logger.debug(
                "Premium label resolution: %d hosts grouped across %d inbounds; squad inbound map: %s",  # noqa: E501
                len(hosts),
                len(hosts_by_inbound),
                {k: len(v) for k, v in squad_inbound_map.items()},
            )
        except Exception:
            logger.debug("Failed to load hosts for premium display", exc_info=True)

        def _host_remark(host: dict[str, Any]) -> str:
            for key in ("remark", "name", "label", "title"):
                value = host.get(key)
                if value is None:
                    continue
                candidate = str(value).strip()
                if candidate:
                    return candidate
            return ""

        node_labels: list[str] = []
        for squad_uuid in tariff.premium_squad_uuids:
            squad_uuid_str = str(squad_uuid)
            inbound_uuids = squad_inbound_map.get(squad_uuid_str) or []
            host_labels_for_squad: list[str] = []
            for inbound_uuid in inbound_uuids:
                for host in hosts_by_inbound.get(inbound_uuid, []):
                    remark = _host_remark(host)
                    if remark:
                        host_labels_for_squad.append(remark)

            if host_labels_for_squad:
                node_labels.extend(host_labels_for_squad)
                continue

            try:
                nodes = (
                    await self.panel_service.get_internal_squad_accessible_nodes(squad_uuid) or []
                )
            except Exception:
                logger.debug(
                    "Failed to load accessible nodes for premium squad %s",
                    squad_uuid,
                    exc_info=True,
                )
                nodes = []
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                node_uuid = str(
                    node.get("uuid") or node.get("nodeUuid") or node.get("node_uuid") or ""
                )
                node_name = ""
                for key in (
                    "nodeName",
                    "name",
                    "nodeRemark",
                    "remark",
                    "label",
                    "title",
                    "address",
                    "host",
                ):
                    value = node.get(key)
                    if value is None:
                        continue
                    candidate = str(value).strip()
                    if candidate:
                        node_name = candidate
                        break
                if node_name:
                    label = node_name
                elif node_uuid:
                    label = f"{node_uuid[:8]}..."
                else:
                    continue
                node_labels.append(label)

        squad_labels = [
            squad_name_map.get(str(uuid), f"{str(uuid)[:8]}...")
            for uuid in tariff.premium_squad_uuids
        ]
        payload: dict[str, Any] = {
            "ts": now_ts,
            "squad_uuids": list(tariff.premium_squad_uuids),
            "squad_labels": list(dict.fromkeys(squad_labels)),
            "node_labels": list(dict.fromkeys(node_labels)),
        }
        self._premium_access_cache[cache_key] = payload
        return {
            "squad_uuids": list(payload["squad_uuids"]),
            "squad_labels": list(payload["squad_labels"]),
            "node_labels": list(payload["node_labels"]),
        }

    def _base_hwid_limit_for_tariff(self, tariff: Tariff | None) -> int | None:
        if tariff and tariff.hwid_device_limit is not None:
            return int(tariff.hwid_device_limit)
        value = self.settings.USER_HWID_DEVICE_LIMIT
        return int(value) if value is not None else None

    def _transition_hwid_base_limits(
        self,
        current_base_limit: int | None,
        target_tariff: Tariff | None,
        *,
        apply_tariff_hwid_limit: bool = False,
    ) -> tuple[int | None, int | None]:
        """Return ``(local_base, panel_base)`` for tariff/admin transitions."""
        target_base_limit = self._base_hwid_limit_for_tariff(target_tariff)
        if apply_tariff_hwid_limit:
            return target_base_limit, target_base_limit
        if current_base_limit is None:
            return None, target_base_limit
        current_base_int = int(current_base_limit)
        return current_base_int, current_base_int

    @staticmethod
    def _tariff_effective_monthly_price(tariff: Tariff, currency: str) -> float | None:
        one_month = tariff.period_price(1, currency)
        if one_month and one_month > 0:
            return float(one_month)
        monthly_prices = []
        for months in tariff.enabled_periods:
            price = tariff.period_price(months, currency)
            if price and price > 0:
                monthly_prices.append(float(price) / max(1, int(months)))
        return min(monthly_prices) if monthly_prices else None

    @staticmethod
    def _effective_hwid_limit(base_limit: int | None, extra_devices: int = 0) -> int | None:
        if base_limit is None:
            return 0
        base_int = max(0, int(base_limit))
        if base_int == 0:
            return 0
        return base_int + max(0, int(extra_devices or 0))

    def calculate_tariff_switch_options(
        self, sub: Subscription, target_tariff: Tariff
    ) -> dict[str, Any]:
        current_tariff = (
            self._resolve_tariff(sub.tariff_key) if sub.tariff_key else self._default_tariff()
        )
        now = datetime.now(UTC)
        remaining_days = max(0, (sub.end_date - now).days) if sub.end_date else 0
        current_model = current_tariff.billing_model if current_tariff else "period"
        default_currency = default_currency_key_for_settings(self.settings)
        effective = float(sub.effective_monthly_price_rub or 0)
        if effective <= 0 and current_model == "period" and current_tariff is not None:
            effective = self._tariff_effective_monthly_price(current_tariff, default_currency) or 0

        if current_model == "period" and target_tariff.billing_model == "period":
            target_monthly = (
                self._tariff_effective_monthly_price(target_tariff, default_currency)
                or effective
                or 1
            )
            remaining_value = remaining_days * (effective / 30) if effective else 0
            days_after = (
                math.floor((remaining_value / float(target_monthly)) * 30)
                if target_monthly
                else remaining_days
            )
            paid_diff = (
                max(0, math.ceil((float(target_monthly) - effective) * remaining_days / 30))
                if effective
                else 0
            )
            return {
                "mode": "period_to_period",
                "remaining_days": remaining_days,
                "recalc_days": max(0, days_after),
                "paid_diff_rub": paid_diff,
                "paid_diff": paid_diff,
                "target_monthly_rub": float(target_monthly),
                "target_monthly_price": float(target_monthly),
                "currency": default_currency,
            }

        if current_model == "period" and target_tariff.billing_model == "traffic":
            rub_per_gb = target_tariff.currency_per_gb_for_conversion(default_currency)
            remaining_value = remaining_days * (effective / 30) if effective else 0
            converted_gb = math.floor(remaining_value / rub_per_gb) if rub_per_gb else 0
            return {
                "mode": "period_to_traffic",
                "remaining_days": remaining_days,
                "converted_gb": max(0, converted_gb),
                "rub_per_gb": rub_per_gb,
                "currency_per_gb": rub_per_gb,
                "currency": default_currency,
            }

        return {
            "mode": "traffic_to_period",
            "remaining_days": remaining_days,
            "currency": default_currency,
        }

    @staticmethod
    def _aware_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    async def _hwid_conversion_credit(
        self,
        session: AsyncSession,
        sub: Subscription,
        *,
        at: datetime,
    ) -> dict[str, Any]:
        entries = await tariff_dal.get_hwid_device_value_entries(
            session,
            subscription_id=sub.subscription_id,
            at=at,
        )
        value_rub = 0.0
        purchase_ids: list[int] = []
        skipped_devices = 0
        for entry in entries:
            currency = str(entry.get("currency") or "").upper()
            if currency in {"XTR", "STARS", "STAR"}:
                skipped_devices += int(entry.get("purchased_devices") or 0)
                continue
            amount = float(entry.get("amount") or 0)
            if amount <= 0:
                continue
            valid_from = (
                self._aware_utc(entry.get("valid_from"))
                or self._aware_utc(entry.get("created_at"))
                or at
            )
            valid_until = self._aware_utc(entry.get("valid_until"))
            if not valid_until or valid_until <= at or valid_from >= valid_until:
                continue
            total_seconds = max(1.0, (valid_until - valid_from).total_seconds())
            remaining_start = max(at, valid_from)
            remaining_seconds = max(0.0, (valid_until - remaining_start).total_seconds())
            if remaining_seconds <= 0:
                continue
            value_rub += amount * (remaining_seconds / total_seconds)
            purchase_ids.append(int(entry["purchase_id"]))
        return {
            "value_rub": value_rub,
            "purchase_ids": purchase_ids,
            "skipped_devices": skipped_devices,
        }

    async def calculate_tariff_switch_options_with_hwid(
        self,
        session: AsyncSession,
        sub: Subscription,
        target_tariff: Tariff,
    ) -> dict[str, Any]:
        options = dict(self.calculate_tariff_switch_options(sub, target_tariff))
        now = datetime.now(UTC)
        credit = await self._hwid_conversion_credit(session, sub, at=now)
        value_rub = float(credit.get("value_rub") or 0)
        options["converted_hwid_value_rub"] = round(value_rub, 2)
        options["converted_hwid_value"] = round(value_rub, 2)
        options["convertible_hwid_purchase_ids"] = list(credit.get("purchase_ids") or [])
        options["nonconverted_hwid_devices"] = int(credit.get("skipped_devices") or 0)
        if value_rub <= 0:
            return options

        if options.get("mode") == "period_to_period":
            target_monthly = float(options.get("target_monthly_rub") or 0)
            hwid_days = math.floor((value_rub / target_monthly) * 30) if target_monthly > 0 else 0
            options["converted_hwid_days"] = max(0, hwid_days)
            options["recalc_days"] = int(options.get("recalc_days") or 0) + max(0, hwid_days)
            options["paid_diff_rub"] = max(
                0,
                math.ceil(float(options.get("paid_diff_rub") or 0) - value_rub),
            )
            return options

        if options.get("mode") == "period_to_traffic":
            rub_per_gb = float(options.get("rub_per_gb") or 0)
            hwid_gb = math.floor(value_rub / rub_per_gb) if rub_per_gb > 0 else 0
            options["converted_hwid_gb"] = max(0, hwid_gb)
            options["converted_gb"] = int(options.get("converted_gb") or 0) + max(0, hwid_gb)
        return options
