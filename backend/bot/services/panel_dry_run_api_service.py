import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from config.settings import Settings
from config.traffic_strategy import (
    REMNAWAVE_TRAFFIC_LIMIT_STRATEGIES,
    canonical_traffic_limit_strategy,
)

from .panel_api_service import PanelApiService

logger = logging.getLogger(__name__)

_USER_ACTION_RE = re.compile(
    r"^/users/(?P<user_uuid>[^/]+)/actions/(?P<action>enable|disable|reset-traffic)$"
)
_NODE_RESTART_RE = re.compile(r"^/nodes/(?P<node_uuid>[^/]+)/actions/restart$")
_INTERNAL_SQUAD_BULK_RE = re.compile(
    r"^/internal-squads/(?P<squad_uuid>[^/]+)/bulk-actions/"
    r"(?P<action>add-users|remove-users)$"
)
_LIVE_POST_ENDPOINTS = frozenset({"/system/tools/happ/encrypt"})
_KNOWN_TRAFFIC_STRATEGIES = REMNAWAVE_TRAFFIC_LIMIT_STRATEGIES

# Constant path templates for intercepted endpoints. The logged path is rebuilt
# from these literals (never from the raw endpoint) so user/squad UUIDs and any
# other id-like segment can never reach the log as clear text.
_USER_ACTION_TEMPLATES = {
    "enable": "/users/<id>/actions/enable",
    "disable": "/users/<id>/actions/disable",
    "reset-traffic": "/users/<id>/actions/reset-traffic",
}
_SQUAD_BULK_TEMPLATES = {
    "add-users": "/internal-squads/<id>/bulk-actions/add-users",
    "remove-users": "/internal-squads/<id>/bulk-actions/remove-users",
}
# Exact intercepted endpoints that carry no id and are safe to log verbatim.
# Mapped to themselves so the logged value comes from this literal table, not
# from the (tainted) request endpoint.
_SAFE_LITERAL_ENDPOINTS = {
    "/users": "/users",
    "/hwid/devices/delete": "/hwid/devices/delete",
}

# Panel payloads can carry proxy credentials (e.g. trojanPassword, ssPassword,
# vless/vmess uuids) and PII (email, telegramId). Redact such values before they
# reach the dry-run log so secrets are never written in clear text.
_SENSITIVE_KEY_RE = re.compile(
    r"pass|pwd|secret|token|key|credential|auth|cookie|session|"
    r"email|mail|phone|telegram|mnemonic",
    re.IGNORECASE,
)
# Field names the dry-run validator understands. Keys are echoed into the log
# only via this table (value == name), so the logged key is always a literal and
# never the raw, source-derived dict key. Unknown keys collapse to "<field>".
_FIELD_LABELS = {
    name: name
    for name in (
        "uuid",
        "username",
        "status",
        "expireAt",
        "trafficLimitBytes",
        "trafficLimitStrategy",
        "hwidDeviceLimit",
        "telegramId",
        "email",
        "description",
        "tag",
        "activeInternalSquads",
        "activeUserInbounds",
        "externalSquadUuid",
        "userUuid",
        "userUuids",
        "users",
        "hwid",
    )
}
_REDACTED = "***"
_UNKNOWN_FIELD = "<field>"
_UNKNOWN_ENDPOINT = "<other>"


@dataclass
class _DryRunValidation:
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, message: str) -> None:
        self.errors.append(message)


class PanelDryRunApiService(PanelApiService):
    """Panel API client that reads live data but never mutates Remnawave users."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._synthetic_users: Dict[str, Dict[str, Any]] = {}

    async def _request(
        self, method: str, endpoint: str, log_full_response: bool = False, **kwargs: Any
    ) -> Optional[Dict[str, Any]]:
        method_upper = method.upper()
        normalized_endpoint = self._normalize_endpoint(endpoint)
        if not self._should_intercept(method_upper, normalized_endpoint):
            result = await super()._request(
                method_upper,
                endpoint,
                log_full_response=log_full_response,
                **kwargs,
            )
            return result if isinstance(result, dict) else None

        validation = await self._validate_dry_run_request(
            method_upper,
            normalized_endpoint,
            kwargs.get("json"),
        )
        if not validation.ok:
            self._log_dry_run(
                "BLOCKED",
                method_upper,
                normalized_endpoint,
                kwargs.get("json"),
                errors=validation.errors,
            )
            return {
                "error": True,
                "status_code": 400,
                "errorCode": "DRY_RUN_VALIDATION_FAILED",
                "message": "Panel dry-run validation failed.",
                "details": {"errors": validation.errors},
            }

        response = await self._dry_run_response(
            method_upper,
            normalized_endpoint,
            kwargs.get("json"),
        )
        self._log_dry_run("OK", method_upper, normalized_endpoint, kwargs.get("json"))
        return {"response": response, "dryRun": True}

    @staticmethod
    def _normalize_endpoint(endpoint: str) -> str:
        return f"/{str(endpoint or '').lstrip('/')}"

    @staticmethod
    def _safe_endpoint(endpoint: str) -> str:
        """Map the request path to a constant log label.

        Every return value comes from a literal template/table, never from the
        (tainted) endpoint itself, so user/squad UUIDs and any other id-like
        segment can never reach the log as clear text. The raw path is only
        matched against, not echoed.
        """
        raw = str(endpoint or "")
        if match := _USER_ACTION_RE.match(raw):
            return _USER_ACTION_TEMPLATES.get(match.group("action"), "/users/<id>/actions/<action>")
        if match := _INTERNAL_SQUAD_BULK_RE.match(raw):
            return _SQUAD_BULK_TEMPLATES.get(
                match.group("action"), "/internal-squads/<id>/bulk-actions/<action>"
            )
        literal = _SAFE_LITERAL_ENDPOINTS.get(raw)
        if literal is not None:
            return literal
        if raw.startswith("/users/"):
            return "/users/<id>"
        if raw.startswith("/internal-squads/"):
            return "/internal-squads/<id>"
        return _UNKNOWN_ENDPOINT

    @staticmethod
    def _summarize_leaf(value: Any) -> Any:
        """Reduce a scalar to a non-sensitive type token.

        Leaf values can carry PII or proxy credentials, so the log never echoes
        them — only their JSON type. ``None`` is kept so absent fields stay
        distinguishable from present ones.
        """
        if value is None:
            return None
        if isinstance(value, bool):
            return "<bool>"
        if isinstance(value, int):
            return "<int>"
        if isinstance(value, float):
            return "<float>"
        if isinstance(value, str):
            return "<str>"
        return f"<{type(value).__name__}>"

    @staticmethod
    def _safe_key(key: Any) -> str:
        """Return a constant label for a payload key.

        Known field names are echoed from the ``_FIELD_LABELS`` table (the value,
        not the source-derived key); anything else collapses to ``<field>``. This
        keeps the raw dict key out of the log entirely.
        """
        if isinstance(key, str):
            return _FIELD_LABELS.get(key, _UNKNOWN_FIELD)
        return _UNKNOWN_FIELD

    @classmethod
    def _redact(cls, value: Any, _depth: int = 0) -> Any:
        """Recursively summarize values, keeping only the JSON shape.

        Keys are replaced by constant labels, sensitive keys collapse to a
        placeholder, and every scalar leaf becomes a type token. The result shows
        which fields a mutation would touch without logging any source-derived
        string (key or value).
        """
        if _depth > 6:
            return "..."
        if isinstance(value, dict):
            return {
                cls._safe_key(k): (
                    _REDACTED
                    if isinstance(k, str) and _SENSITIVE_KEY_RE.search(k)
                    else cls._redact(v, _depth + 1)
                )
                for k, v in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [cls._redact(item, _depth + 1) for item in value]
        return cls._summarize_leaf(value)

    @classmethod
    def _payload_preview(cls, payload: Any) -> str:
        redacted = cls._redact(payload)
        try:
            text = json.dumps(redacted, ensure_ascii=False, default=str, sort_keys=True)
        except Exception:
            text = str(redacted)
        if len(text) > 1200:
            return f"{text[:1200]}..."
        return text

    def _log_dry_run(
        self,
        status: str,
        method: str,
        endpoint: str,
        payload: Any,
        *,
        errors: Optional[List[str]] = None,
    ) -> None:
        logger.info(
            "[PANEL DRY-RUN %s] would %s %s payload=%s%s",
            status,
            method,
            self._safe_endpoint(endpoint),
            self._payload_preview(payload),
            f" errors={errors}" if errors else "",
        )

    @staticmethod
    def _should_intercept(method: str, endpoint: str) -> bool:
        if method in PanelApiService._SAFE_METHODS:
            return False
        if method == "POST" and endpoint in _LIVE_POST_ENDPOINTS:
            return False
        return True

    async def _validate_dry_run_request(
        self,
        method: str,
        endpoint: str,
        payload: Any,
    ) -> _DryRunValidation:
        validation = _DryRunValidation()
        data = payload if isinstance(payload, dict) else {}
        if payload is not None and not isinstance(payload, dict):
            validation.add("JSON payload must be an object.")
            return validation

        if method == "POST" and endpoint == "/users":
            await self._validate_create_user_payload(data, validation)
            return validation
        if method == "PATCH" and endpoint == "/users":
            await self._validate_update_user_payload(data, validation)
            return validation
        if method == "POST" and (match := _USER_ACTION_RE.match(endpoint)):
            user_uuid = match.group("user_uuid")
            self._validate_non_empty_string(user_uuid, "user uuid", validation)
            await self._validate_remote_user(user_uuid, validation)
            return validation
        if method == "DELETE" and endpoint.startswith("/users/"):
            user_uuid = endpoint.removeprefix("/users/").strip()
            self._validate_non_empty_string(user_uuid, "user uuid", validation)
            await self._validate_remote_user(user_uuid, validation)
            return validation
        if method == "POST" and endpoint == "/hwid/devices/delete":
            user_uuid = self._validate_non_empty_string(
                data.get("userUuid"),
                "userUuid",
                validation,
            )
            self._validate_non_empty_string(data.get("hwid"), "hwid", validation)
            await self._validate_remote_user(user_uuid, validation)
            return validation
        if method == "POST" and (match := _NODE_RESTART_RE.match(endpoint)):
            self._validate_non_empty_string(match.group("node_uuid"), "node uuid", validation)
            self._validate_bool(data.get("forceRestart"), "forceRestart", validation)
            return validation
        if method == "POST" and endpoint == "/nodes/actions/restart-all":
            self._validate_bool(data.get("forceRestart"), "forceRestart", validation)
            return validation
        if match := _INTERNAL_SQUAD_BULK_RE.match(endpoint):
            squad_uuid = match.group("squad_uuid")
            self._validate_non_empty_string(squad_uuid, "squad uuid", validation)
            user_uuids = self._validate_string_list(data.get("userUuids"), "userUuids", validation)
            if not user_uuids:
                user_uuids = self._validate_string_list(data.get("users"), "users", validation)
            await self._validate_remote_squads([squad_uuid], validation)
            for user_uuid in user_uuids:
                await self._validate_remote_user(user_uuid, validation)
            return validation

        if payload is None:
            return validation
        self._validate_json_serializable(payload, validation)
        return validation

    async def _validate_create_user_payload(
        self,
        payload: Dict[str, Any],
        validation: _DryRunValidation,
    ) -> None:
        username = self._validate_non_empty_string(payload.get("username"), "username", validation)
        if username and (
            not (3 <= len(username) <= 36) or not re.match(r"^[A-Za-z0-9_-]+$", username)
        ):
            validation.add("username must be 3-36 chars and contain only A-Z, 0-9, _ or -.")
        self._validate_user_mutation_payload(payload, validation, require_uuid=False)
        await self._validate_remote_squads(
            self._validate_string_list(
                payload.get("activeInternalSquads"),
                "activeInternalSquads",
                validation,
                required=False,
            ),
            validation,
        )
        if not bool(getattr(self.settings, "PANEL_DRY_RUN_SYNTHETIC_CREATE", True)):
            validation.add("PANEL_DRY_RUN_SYNTHETIC_CREATE is disabled.")
        if self._remote_validation_enabled and username:
            await self._validate_create_uniqueness(payload, validation)

    async def _validate_update_user_payload(
        self,
        payload: Dict[str, Any],
        validation: _DryRunValidation,
    ) -> None:
        user_uuid = self._validate_non_empty_string(payload.get("uuid"), "uuid", validation)
        self._validate_user_mutation_payload(payload, validation, require_uuid=True)
        await self._validate_remote_user(user_uuid, validation)
        await self._validate_remote_squads(
            self._validate_string_list(
                payload.get("activeInternalSquads"),
                "activeInternalSquads",
                validation,
                required=False,
            ),
            validation,
        )

    def _validate_user_mutation_payload(
        self,
        payload: Dict[str, Any],
        validation: _DryRunValidation,
        *,
        require_uuid: bool,
    ) -> None:
        if require_uuid:
            self._validate_non_empty_string(payload.get("uuid"), "uuid", validation)
        if "expireAt" in payload:
            self._validate_datetime(payload.get("expireAt"), "expireAt", validation)
        if "trafficLimitBytes" in payload:
            self._validate_non_negative_int(
                payload.get("trafficLimitBytes"),
                "trafficLimitBytes",
                validation,
            )
        if "trafficLimitStrategy" in payload:
            strategy = self._validate_non_empty_string(
                payload.get("trafficLimitStrategy"),
                "trafficLimitStrategy",
                validation,
            )
            normalized_strategy = canonical_traffic_limit_strategy(strategy)
            if strategy and normalized_strategy not in _KNOWN_TRAFFIC_STRATEGIES:
                validation.add(f"trafficLimitStrategy {strategy!r} is not supported.")
            elif strategy:
                payload["trafficLimitStrategy"] = normalized_strategy
        if "hwidDeviceLimit" in payload:
            self._validate_non_negative_int(
                payload.get("hwidDeviceLimit"),
                "hwidDeviceLimit",
                validation,
            )
        if "telegramId" in payload:
            self._validate_positive_int(payload.get("telegramId"), "telegramId", validation)
        if "email" in payload and payload.get("email") is not None:
            self._validate_non_empty_string(payload.get("email"), "email", validation)
        if "externalSquadUuid" in payload and payload.get("externalSquadUuid") is not None:
            self._validate_non_empty_string(
                payload.get("externalSquadUuid"),
                "externalSquadUuid",
                validation,
            )
        self._validate_json_serializable(payload, validation)

    @property
    def _remote_validation_enabled(self) -> bool:
        return bool(getattr(self.settings, "PANEL_DRY_RUN_VALIDATE_REMOTE", True))

    async def _validate_remote_user(
        self,
        user_uuid: Optional[str],
        validation: _DryRunValidation,
    ) -> Optional[Dict[str, Any]]:
        if not user_uuid or not self._remote_validation_enabled:
            return self._synthetic_users.get(str(user_uuid or ""))
        user = self._synthetic_users.get(str(user_uuid))
        if user:
            return user
        try:
            user = await super().get_user_by_uuid(str(user_uuid), log_response=False)
        except Exception as exc:
            validation.add(f"failed to validate panel user {user_uuid}: {type(exc).__name__}")
            return None
        if not user:
            validation.add(f"panel user {user_uuid} was not found.")
        return user if isinstance(user, dict) else None

    async def _validate_remote_squads(
        self,
        squad_uuids: List[str],
        validation: _DryRunValidation,
    ) -> None:
        if not squad_uuids or not self._remote_validation_enabled:
            return
        try:
            squads = await super().get_internal_squads()
        except Exception as exc:
            validation.add(f"failed to validate panel squads: {type(exc).__name__}")
            return
        if squads is None:
            validation.add("failed to validate panel squads: empty panel response.")
            return
        known = {
            str(squad.get("uuid") or squad.get("id") or "").strip()
            for squad in squads
            if isinstance(squad, dict)
        }
        missing = sorted({squad_uuid for squad_uuid in squad_uuids if squad_uuid not in known})
        if missing:
            validation.add(f"panel squads were not found: {', '.join(missing)}.")

    async def _validate_create_uniqueness(
        self,
        payload: Dict[str, Any],
        validation: _DryRunValidation,
    ) -> None:
        checks = (
            ("username", "username", payload.get("username")),
            ("telegramId", "telegram_id", payload.get("telegramId")),
            ("email", "email", payload.get("email")),
        )
        for label, argument_name, value in checks:
            if value in (None, ""):
                continue
            try:
                if argument_name == "username":
                    users = await super().get_users_by_filter(username=str(value))
                elif argument_name == "telegram_id":
                    users = await super().get_users_by_filter(telegram_id=int(str(value)))
                else:
                    users = await super().get_users_by_filter(email=str(value))
            except Exception as exc:
                validation.add(f"failed to validate unique {label}: {type(exc).__name__}")
                continue
            if users:
                validation.add(f"panel user with {label} {value!r} already exists.")

    @staticmethod
    def _validate_non_empty_string(
        value: Any,
        name: str,
        validation: _DryRunValidation,
    ) -> Optional[str]:
        if not isinstance(value, str) or not value.strip():
            validation.add(f"{name} must be a non-empty string.")
            return None
        return value.strip()

    @staticmethod
    def _validate_string_list(
        value: Any,
        name: str,
        validation: _DryRunValidation,
        *,
        required: bool = True,
    ) -> List[str]:
        if value is None:
            if required:
                validation.add(f"{name} must be a list of strings.")
            return []
        if not isinstance(value, list):
            validation.add(f"{name} must be a list of strings.")
            return []
        result = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                validation.add(f"{name} contains an empty or non-string value.")
                continue
            result.append(item.strip())
        return result

    @staticmethod
    def _validate_non_negative_int(
        value: Any,
        name: str,
        validation: _DryRunValidation,
    ) -> None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            validation.add(f"{name} must be an integer.")
            return
        if parsed < 0:
            validation.add(f"{name} must be >= 0.")

    @staticmethod
    def _validate_positive_int(value: Any, name: str, validation: _DryRunValidation) -> None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            validation.add(f"{name} must be an integer.")
            return
        if parsed <= 0:
            validation.add(f"{name} must be > 0.")

    @staticmethod
    def _validate_bool(value: Any, name: str, validation: _DryRunValidation) -> None:
        if not isinstance(value, bool):
            validation.add(f"{name} must be a boolean.")

    @staticmethod
    def _validate_datetime(value: Any, name: str, validation: _DryRunValidation) -> None:
        if not isinstance(value, str) or not value.strip():
            validation.add(f"{name} must be an ISO datetime string.")
            return
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            validation.add(f"{name} must be a valid ISO datetime string.")

    @staticmethod
    def _validate_json_serializable(value: Any, validation: _DryRunValidation) -> None:
        try:
            json.dumps(value, default=str)
        except (TypeError, ValueError):
            validation.add("payload must be JSON serializable.")

    async def _dry_run_response(
        self,
        method: str,
        endpoint: str,
        payload: Any,
    ) -> Dict[str, Any]:
        data = payload if isinstance(payload, dict) else {}
        if method == "POST" and endpoint == "/users":
            return self._dry_run_create_user_response(data)
        if method == "PATCH" and endpoint == "/users":
            return await self._dry_run_patch_user_response(data)
        if method == "POST" and (match := _USER_ACTION_RE.match(endpoint)):
            return self._dry_run_user_action_response(
                match.group("user_uuid"),
                match.group("action"),
            )
        if method == "DELETE" and endpoint.startswith("/users/"):
            return {"uuid": endpoint.removeprefix("/users/"), "deleted": True, "dryRun": True}
        if method == "POST" and endpoint == "/hwid/devices/delete":
            return {"userUuid": data.get("userUuid"), "hwid": data.get("hwid"), "dryRun": True}
        if method == "POST" and (match := _NODE_RESTART_RE.match(endpoint)):
            return {
                "uuid": match.group("node_uuid"),
                "forceRestart": data.get("forceRestart"),
                "dryRun": True,
            }
        if method == "POST" and endpoint == "/nodes/actions/restart-all":
            return {"forceRestart": data.get("forceRestart"), "dryRun": True}
        if match := _INTERNAL_SQUAD_BULK_RE.match(endpoint):
            return {
                "squadUuid": match.group("squad_uuid"),
                "action": match.group("action"),
                "users": data.get("userUuids") or data.get("users") or [],
                "dryRun": True,
            }
        return {"dryRun": True}

    def _dry_run_create_user_response(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        identity = ":".join(
            str(payload.get(key) or "") for key in ("username", "telegramId", "email")
        )
        user_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"remnawave-minishop:dry-run:{identity}"))
        short_uuid = user_uuid.split("-")[0]
        response = {
            **payload,
            "uuid": user_uuid,
            "shortUuid": short_uuid,
            "subscriptionUuid": short_uuid,
            "subscriptionUrl": self._subscription_url(short_uuid),
            "dryRun": True,
        }
        self._synthetic_users[user_uuid] = response
        return response

    async def _dry_run_patch_user_response(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        user_uuid = str(payload.get("uuid") or "")
        existing = self._synthetic_users.get(user_uuid)
        if not existing and self._remote_validation_enabled:
            try:
                existing = await super().get_user_by_uuid(user_uuid, log_response=False)
            except Exception:
                existing = None
        response = {**(existing or {"uuid": user_uuid}), **payload, "dryRun": True}
        if user_uuid in self._synthetic_users:
            self._synthetic_users[user_uuid] = response
        return response

    @staticmethod
    def _dry_run_user_action_response(user_uuid: str, action: str) -> Dict[str, Any]:
        response: Dict[str, Any] = {"uuid": user_uuid, "action": action, "dryRun": True}
        if action == "enable":
            response["status"] = "ACTIVE"
        elif action == "disable":
            response["status"] = "DISABLED"
        elif action == "reset-traffic":
            response["userTraffic"] = {"usedTrafficBytes": 0}
        return response

    def _subscription_url(self, short_uuid: str) -> Optional[str]:
        panel_api_url = self.settings.panel_settings.api_url
        if not panel_api_url:
            return None
        return f"{panel_api_url.rstrip('/')}/sub/{short_uuid}"
