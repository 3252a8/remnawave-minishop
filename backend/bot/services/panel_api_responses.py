"""Shared classification helpers for Remnawave API responses."""

from typing import Any

_USER_NOT_FOUND_ERROR_CODES = frozenset(
    ("A025", "A062", "A063", "USER_NOT_FOUND", "USERS_NOT_FOUND", "NOT_FOUND")
)


class PanelApiResponseMixin:
    @staticmethod
    def _panel_response_details(response_data: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(response_data, dict):
            return {}
        details = response_data.get("details")
        return details if isinstance(details, dict) else {}

    @classmethod
    def _panel_response_error_code(cls, response_data: dict[str, Any] | None) -> str | None:
        if not isinstance(response_data, dict):
            return None
        details = cls._panel_response_details(response_data)
        error_code = (
            response_data.get("errorCode")
            or response_data.get("code")
            or details.get("errorCode")
            or details.get("code")
        )
        return str(error_code).strip().upper() if error_code else None

    @classmethod
    def _panel_response_message(cls, response_data: dict[str, Any] | None) -> str | None:
        if not isinstance(response_data, dict):
            return None
        details = cls._panel_response_details(response_data)
        message = (
            response_data.get("message")
            or details.get("message")
            or details.get("error")
            or details.get("raw_response_text")
        )
        if message is None:
            return None
        message = str(message).replace("\n", " ").strip()
        return message[:500] if message else None

    @classmethod
    def _is_user_not_found_response(cls, response_data: dict[str, Any] | None) -> bool:
        if not isinstance(response_data, dict):
            return False
        error_code = cls._panel_response_error_code(response_data)
        return error_code in _USER_NOT_FOUND_ERROR_CODES or response_data.get("status_code") == 404

    @classmethod
    def _describe_user_lookup_failure(
        cls,
        response_data: dict[str, Any] | None,
        *,
        not_found: bool,
    ) -> str:
        if not isinstance(response_data, dict):
            return "classification=panel_lookup_failed response=empty"

        classification = "confirmed_not_found" if not_found else "panel_lookup_failed"
        parts = [f"classification={classification}"]
        status_code = response_data.get("status_code")
        if status_code is not None:
            parts.append(f"status_code={status_code}")
        error_code = cls._panel_response_error_code(response_data)
        if error_code:
            parts.append(f"error_code={error_code}")
        message = cls._panel_response_message(response_data)
        if message:
            parts.append(f"message={message}")
        return " ".join(parts)

    @classmethod
    def _is_missing_endpoint_response(cls, response_data: dict[str, Any] | None) -> bool:
        """Return whether the panel build does not expose the requested route."""
        if not isinstance(response_data, dict) or response_data.get("status_code") != 404:
            return False
        if cls._panel_response_error_code(response_data):
            return False
        message = (cls._panel_response_message(response_data) or "").lower()
        return "cannot post" in message or "cannot get" in message or "not found" in message
