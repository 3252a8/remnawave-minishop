import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from config.traffic_strategy import normalize_traffic_limit_strategy

from ._typing import SubscriptionServiceMixinContract
from .squad_overrides import (
    normalize_panel_external_squad_uuid,
    normalize_panel_internal_squad_uuids,
)

logger = logging.getLogger(__name__)


class SubscriptionLifecyclePanelMixin(SubscriptionServiceMixinContract):
    async def _lookup_panel_user_for_subscription_details(
        self,
        panel_user_uuid: str,
    ) -> tuple[dict[str, Any] | None, bool, str]:
        lookup_method = getattr(self.panel_service, "get_user_by_uuid_lookup", None)
        if callable(lookup_method):
            try:
                lookup = await lookup_method(panel_user_uuid, log_response=False)
            except TypeError:
                try:
                    lookup = await lookup_method(panel_user_uuid)
                except Exception as exc:
                    logger.exception(
                        "Failed to fetch panel user %s for subscription details",
                        panel_user_uuid,
                    )
                    return None, False, self._panel_lookup_exception_reason(exc)
            except Exception as exc:
                logger.exception(
                    "Failed to fetch panel user %s for subscription details",
                    panel_user_uuid,
                )
                return None, False, self._panel_lookup_exception_reason(exc)

            if isinstance(lookup, dict) and ("ok" in lookup or "not_found" in lookup):
                user = lookup.get("user")
                if lookup.get("ok") and isinstance(user, dict):
                    return user, False, ""
                reason = str(lookup.get("failure_reason") or "classification=panel_lookup_failed")
                return None, bool(lookup.get("not_found")), reason

        try:
            panel_user = await self.panel_service.get_user_by_uuid(panel_user_uuid)
        except Exception as exc:
            logger.exception(
                "Failed to fetch panel user %s for subscription details",
                panel_user_uuid,
            )
            return None, False, self._panel_lookup_exception_reason(exc)
        return (panel_user if isinstance(panel_user, dict) else None), False, ""

    @staticmethod
    def _panel_lookup_exception_reason(exc: Exception) -> str:
        message = str(exc).replace("\n", " ").strip()
        if len(message) > 300:
            message = f"{message[:300]}..."
        reason = f"classification=panel_lookup_failed exception={type(exc).__name__}"
        if message:
            reason = f"{reason} message={message}"
        return reason

    @staticmethod
    def _display_datetime_text(value: Any | None) -> str | None:
        if not value:
            return None
        if isinstance(value, datetime):
            normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
            return normalized.strftime("%d.%m.%Y %H:%M")
        return str(value)

    @staticmethod
    def _panel_expiry_matches(raw_expire_at: Any | None, expected_expire_at: datetime) -> bool:
        if not raw_expire_at:
            return False
        try:
            panel_expire_at = datetime.fromisoformat(str(raw_expire_at).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            logger.warning(
                "Panel update returned unparsable expireAt=%r for expected expiry %s.",
                raw_expire_at,
                expected_expire_at.isoformat(),
            )
            return False
        expected = (
            expected_expire_at
            if expected_expire_at.tzinfo
            else expected_expire_at.replace(tzinfo=UTC)
        )
        actual = panel_expire_at if panel_expire_at.tzinfo else panel_expire_at.replace(tzinfo=UTC)
        return abs((actual - expected).total_seconds()) <= 1

    @classmethod
    def _panel_entitlement_mismatches(
        cls,
        panel_user: dict[str, Any] | None,
        expected_payload: dict[str, Any],
    ) -> list[str]:
        if not isinstance(panel_user, dict):
            return ["panel_user"]
        if panel_user.get("error"):
            return ["panel_error"]

        mismatches: list[str] = []
        if "uuid" in expected_payload:
            actual_uuid = str(panel_user.get("uuid") or "").strip()
            expected_uuid = str(expected_payload.get("uuid") or "").strip()
            if actual_uuid != expected_uuid:
                mismatches.append("uuid")

        expected_expiry = expected_payload.get("expireAt")
        if expected_expiry is not None:
            if isinstance(expected_expiry, datetime):
                expected_expiry_dt = expected_expiry
            else:
                try:
                    expected_expiry_dt = datetime.fromisoformat(
                        str(expected_expiry).replace("Z", "+00:00")
                    )
                except (TypeError, ValueError):
                    expected_expiry_dt = None
            if expected_expiry_dt is None or not cls._panel_expiry_matches(
                panel_user.get("expireAt"),
                expected_expiry_dt,
            ):
                mismatches.append("expireAt")

        for field_name in ("trafficLimitBytes", "hwidDeviceLimit"):
            if field_name not in expected_payload:
                continue
            actual_raw = panel_user.get(field_name)
            expected_raw = expected_payload.get(field_name)
            if actual_raw is None or expected_raw is None:
                mismatches.append(field_name)
                continue
            try:
                actual_value = int(actual_raw)
                expected_value = int(expected_raw)
            except (TypeError, ValueError):
                mismatches.append(field_name)
                continue
            if actual_value != expected_value:
                mismatches.append(field_name)

        if "trafficLimitStrategy" in expected_payload:
            actual_strategy = panel_user.get("trafficLimitStrategy")
            if actual_strategy is None:
                traffic_stats = panel_user.get("userTraffic")
                if isinstance(traffic_stats, dict):
                    actual_strategy = traffic_stats.get("trafficLimitStrategy")
            if normalize_traffic_limit_strategy(
                actual_strategy,
                default=None,
            ) != normalize_traffic_limit_strategy(
                expected_payload.get("trafficLimitStrategy"),
                default=None,
            ):
                mismatches.append("trafficLimitStrategy")

        if "activeInternalSquads" in expected_payload:
            actual_squads = normalize_panel_internal_squad_uuids(panel_user)
            expected_squads = normalize_panel_internal_squad_uuids(
                {"activeInternalSquads": expected_payload.get("activeInternalSquads")}
            )
            if actual_squads is None or set(actual_squads) != set(expected_squads or []):
                mismatches.append("activeInternalSquads")

        if "externalSquadUuid" in expected_payload:
            actual_external_present, actual_external_uuid = normalize_panel_external_squad_uuid(
                panel_user
            )
            expected_external_uuid = (
                str(expected_payload.get("externalSquadUuid") or "").strip() or None
            )
            if not actual_external_present or actual_external_uuid != expected_external_uuid:
                mismatches.append("externalSquadUuid")

        if "status" in expected_payload:
            actual_status = str(panel_user.get("status") or "").strip().upper()
            expected_status = str(expected_payload.get("status") or "").strip().upper()
            if actual_status != expected_status:
                mismatches.append("status")

        return mismatches

    async def _get_panel_user_for_entitlement_verification(
        self,
        panel_user_uuid: str,
    ) -> dict[str, Any] | None:
        try:
            try:
                panel_user = await self.panel_service.get_user_by_uuid(
                    panel_user_uuid,
                    log_response=False,
                    use_cache=False,
                )
            except TypeError:
                try:
                    panel_user = await self.panel_service.get_user_by_uuid(
                        panel_user_uuid,
                        log_response=False,
                    )
                except TypeError:
                    panel_user = await self.panel_service.get_user_by_uuid(panel_user_uuid)
        except Exception:
            logger.exception(
                "Failed to fetch panel user %s while verifying persisted entitlement.",
                panel_user_uuid,
            )
            return None
        return panel_user if isinstance(panel_user, dict) else None

    async def _confirmed_panel_entitlement(
        self,
        panel_user_uuid: str,
        panel_update_result: dict[str, Any] | None,
        expected_payload: dict[str, Any],
        *,
        source: str,
        verification_attempts: int = 3,
        retry_delay_seconds: float = 0.2,
    ) -> dict[str, Any] | None:
        expected_entitlement = {**expected_payload, "uuid": panel_user_uuid}
        response_user = panel_update_result
        if (
            isinstance(response_user, dict)
            and isinstance(response_user.get("response"), dict)
            and not response_user.get("uuid")
        ):
            response_user = response_user["response"]

        response_mismatches = self._panel_entitlement_mismatches(
            response_user,
            expected_entitlement,
        )
        if response_mismatches:
            logger.info(
                "Panel entitlement response requires persisted verification: source=%s "
                "panel_uuid=%s mismatched_fields=%s",
                source,
                panel_user_uuid,
                ",".join(response_mismatches),
            )

        attempts = max(1, int(verification_attempts))
        delay_seconds = max(0.0, float(retry_delay_seconds))
        persisted_mismatches = response_mismatches
        # A successful PATCH response may only echo the requested values. Finalization
        # must be based on an independent, uncached read of the persisted panel state.
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                try:
                    repair_result = await self.panel_service.update_user_details_on_panel(
                        panel_user_uuid,
                        dict(expected_entitlement),
                    )
                except Exception:
                    logger.exception(
                        "Panel entitlement repair request failed: source=%s panel_uuid=%s "
                        "attempt=%s/%s",
                        source,
                        panel_user_uuid,
                        attempt,
                        attempts,
                    )
                else:
                    repair_mismatches = self._panel_entitlement_mismatches(
                        repair_result,
                        expected_entitlement,
                    )
                    if repair_mismatches:
                        logger.info(
                            "Panel entitlement repair response is incomplete: source=%s "
                            "panel_uuid=%s attempt=%s/%s mismatched_fields=%s",
                            source,
                            panel_user_uuid,
                            attempt,
                            attempts,
                            ",".join(repair_mismatches),
                        )
                if delay_seconds > 0:
                    await asyncio.sleep(delay_seconds * (2 ** (attempt - 2)))

            persisted_user = await self._get_panel_user_for_entitlement_verification(
                panel_user_uuid
            )
            persisted_mismatches = self._panel_entitlement_mismatches(
                persisted_user,
                expected_entitlement,
            )
            if not persisted_mismatches:
                return persisted_user
            if attempt < attempts:
                logger.warning(
                    "Persisted panel entitlement mismatch; retrying update: source=%s "
                    "panel_uuid=%s attempt=%s/%s mismatched_fields=%s",
                    source,
                    panel_user_uuid,
                    attempt,
                    attempts,
                    ",".join(persisted_mismatches),
                )

        logger.warning(
            "Panel entitlement verification failed after retries: source=%s panel_uuid=%s "
            "attempts=%s mismatched_fields=%s",
            source,
            panel_user_uuid,
            attempts,
            ",".join(persisted_mismatches),
        )
        return None

    async def _panel_update_confirms_expiry(
        self,
        panel_user_uuid: str,
        panel_update_result: dict[str, Any] | None,
        expected_expire_at: datetime,
    ) -> bool:
        confirmed = await self._confirmed_panel_entitlement(
            panel_user_uuid,
            panel_update_result,
            {"expireAt": expected_expire_at},
            source="expiry_update",
        )
        return confirmed is not None

    @staticmethod
    def _device_topup_renewal_available(
        extra_hwid_devices: int,
        extra_hwid_valid_until: Any | None,
        subscription_end_date: Any | None,
    ) -> bool:
        if not isinstance(extra_hwid_valid_until, datetime) or not isinstance(
            subscription_end_date, datetime
        ):
            return False
        valid_until = (
            extra_hwid_valid_until
            if extra_hwid_valid_until.tzinfo
            else extra_hwid_valid_until.replace(tzinfo=UTC)
        )
        end_date = (
            subscription_end_date
            if subscription_end_date.tzinfo
            else subscription_end_date.replace(tzinfo=UTC)
        )
        return bool(int(extra_hwid_devices or 0) > 0 and valid_until < end_date)
