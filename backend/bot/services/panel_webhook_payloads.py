import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .hwid_device_webhook import HWID_DEVICE_EVENTS, hwid_device_context_fingerprint
from .torrent_blocker_notifications import torrent_blocker_event_fingerprint
from .torrent_blocker_webhook import TORRENT_BLOCKER_EVENT

EXPIRATION_EVENT = "user.expiration"
ACTIONABLE_EVENTS = frozenset(
    {
        "user.expires_in_72_hours",
        "user.expires_in_48_hours",
        "user.expires_in_24_hours",
        EXPIRATION_EVENT,
        "user.expired",
        "user.expired_24_hours_ago",
    }
)


class PanelWebhookPayloadMixin:
    if TYPE_CHECKING:

        @classmethod
        def _expiration_hours(cls, *args: Any, **kwargs: Any) -> int | None: ...

    @staticmethod
    def _payload_telegram_id(user_payload: dict) -> int | None:
        raw = user_payload.get("telegramId")
        try:
            value = int(raw or 0)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    @staticmethod
    def _payload_panel_uuid(user_payload: dict) -> str:
        return str(
            user_payload.get("uuid")
            or user_payload.get("userUuid")
            or user_payload.get("id")
            or user_payload.get("shortUuid")
            or ""
        ).strip()

    @staticmethod
    def _payload_expire_date(user_payload: dict) -> str:
        return str(user_payload.get("expireAt") or "")[:10]

    @classmethod
    def _payload_log_context(cls, user_payload: dict) -> str:
        telegram_id = cls._payload_telegram_id(user_payload)
        panel_uuid = cls._payload_panel_uuid(user_payload)
        email = cls._mask_email(str(user_payload.get("email") or "").strip())
        expire_at = str(user_payload.get("expireAt") or "").strip()
        payload_keys = ",".join(sorted(str(key) for key in user_payload)) or "none"
        return (
            f"telegramId={telegram_id or 'N/A'} "
            f"panel_uuid={panel_uuid or 'N/A'} "
            f"email={email or 'N/A'} "
            f"expireAt={expire_at or 'N/A'} "
            f"payload_keys={payload_keys}"
        )

    @classmethod
    def _payload_state_snapshot(cls, user_payload: dict[str, Any]) -> str:
        """Mutable panel fields only: enough to diff two events, no personal data."""
        squads = user_payload.get("activeInternalSquads")
        squad_uuids = ",".join(
            sorted(
                str(squad.get("uuid") if isinstance(squad, dict) else squad)
                for squad in (squads if isinstance(squads, list) else [])
            )
        )
        fields = {
            "panel_uuid": cls._payload_panel_uuid(user_payload) or "N/A",
            "status": user_payload.get("status"),
            "expireAt": user_payload.get("expireAt"),
            "trafficLimitBytes": user_payload.get("trafficLimitBytes"),
            "trafficLimitStrategy": user_payload.get("trafficLimitStrategy"),
            "hwidDeviceLimit": user_payload.get("hwidDeviceLimit"),
            "activeInternalSquads": squad_uuids or "none",
            "updatedAt": user_payload.get("updatedAt"),
        }
        return " ".join(f"{key}={value}" for key, value in fields.items())

    @staticmethod
    def _mask_email(email: str) -> str:
        if not email:
            return ""
        local_part, separator, domain = email.partition("@")
        if not separator or not domain:
            return "present"
        visible = local_part[:2] if len(local_part) > 2 else local_part[:1]
        return f"{visible}***@{domain}"

    @staticmethod
    def _payload_expire_datetime(user_payload: dict) -> datetime | None:
        raw = str(user_payload.get("expireAt") or "").strip()
        if not raw:
            return None
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                value = datetime.fromisoformat(raw[:10])
            except ValueError:
                return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _payload_expire_is_date_only(user_payload: dict) -> bool:
        raw = str(user_payload.get("expireAt") or "").strip()
        return len(raw) == 10 and raw[4:5] == "-" and raw[7:8] == "-"

    @classmethod
    def _webhook_meta(
        cls,
        payload: dict[str, Any],
        event_data: dict[str, Any],
    ) -> dict[str, Any]:
        meta: dict[str, Any] = {}
        for source in (payload, event_data):
            for key in ("meta", "_meta"):
                raw = source.get(key)
                if isinstance(raw, dict):
                    meta.update(raw)
        return meta

    @classmethod
    def _webhook_event_id(
        cls,
        event_name: str,
        user_payload: dict[str, Any],
        meta: dict[str, Any] | None = None,
        *,
        context: dict[str, Any] | None = None,
        fingerprint_secret: str | None = None,
    ) -> str:
        subject = (
            cls._payload_telegram_id(user_payload)
            or cls._payload_panel_uuid(user_payload)
            or "unknown"
        )
        event_id = f"{event_name}:{subject}"
        if event_name == EXPIRATION_EVENT:
            expiration_hours = cls._expiration_hours(meta, user_payload)
            if expiration_hours is not None:
                event_id = f"{event_id}:expiration:{expiration_hours}"
        elif event_name == TORRENT_BLOCKER_EVENT:
            fingerprint = torrent_blocker_event_fingerprint(
                context or {},
                secret=fingerprint_secret or "",
            )
            event_id = f"{event_id}:{fingerprint}"
        elif event_name in HWID_DEVICE_EVENTS:
            fingerprint = hwid_device_context_fingerprint(context)
            if fingerprint:
                event_id = f"{event_id}:{fingerprint}"
            else:
                event_id = f"{event_id}:{cls._payload_fingerprint(user_payload, meta)}"
        elif event_name not in ACTIONABLE_EVENTS:
            event_id = f"{event_id}:{cls._payload_fingerprint(user_payload, meta)}"
        return event_id

    @staticmethod
    def _payload_fingerprint(
        user_payload: dict[str, Any],
        meta: dict[str, Any] | None,
    ) -> str:
        try:
            normalized = json.dumps(
                {"user": user_payload, "meta": meta or {}},
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
        except (TypeError, ValueError):
            normalized = repr(sorted(user_payload.items()))
        return hashlib.sha256(normalized.encode()).hexdigest()[:24]
