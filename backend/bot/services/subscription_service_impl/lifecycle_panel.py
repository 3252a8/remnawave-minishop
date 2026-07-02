import logging
from datetime import UTC, datetime
from typing import Any

from ._typing import SubscriptionServiceMixinContract


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
                    logging.exception(
                        "Failed to fetch panel user %s for subscription details",
                        panel_user_uuid,
                    )
                    return None, False, self._panel_lookup_exception_reason(exc)
            except Exception as exc:
                logging.exception(
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
            logging.exception(
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
            logging.warning(
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

    async def _panel_update_confirms_expiry(
        self,
        panel_user_uuid: str,
        panel_update_result: dict[str, Any] | None,
        expected_expire_at: datetime,
    ) -> bool:
        if not panel_update_result:
            return False
        if isinstance(panel_update_result, dict):
            if panel_update_result.get("error"):
                return False
            raw_expire_at = panel_update_result.get("expireAt")
            if raw_expire_at and self._panel_expiry_matches(raw_expire_at, expected_expire_at):
                return True

            if raw_expire_at:
                logging.warning(
                    "Panel update response expiry mismatch for user %s: expireAt=%r "
                    "expected=%s. Fetching panel user to verify persisted state.",
                    panel_user_uuid,
                    raw_expire_at,
                    expected_expire_at.isoformat(),
                )
            else:
                logging.info(
                    "Panel update response for user %s did not include expireAt. "
                    "Fetching panel user to verify persisted state.",
                    panel_user_uuid,
                )
        else:
            logging.warning(
                "Panel update response for user %s had unexpected type %s. "
                "Fetching panel user to verify persisted state.",
                panel_user_uuid,
                type(panel_update_result).__name__,
            )

        try:
            try:
                panel_user = await self.panel_service.get_user_by_uuid(
                    panel_user_uuid,
                    log_response=False,
                )
            except TypeError:
                panel_user = await self.panel_service.get_user_by_uuid(panel_user_uuid)
        except Exception:
            logging.exception(
                "Failed to verify panel expiry for user %s after update.",
                panel_user_uuid,
            )
            return False

        if not isinstance(panel_user, dict):
            logging.warning(
                "Panel expiry verification for user %s returned unexpected payload: %r",
                panel_user_uuid,
                panel_user,
            )
            return False
        return self._panel_expiry_matches(panel_user.get("expireAt"), expected_expire_at)

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
