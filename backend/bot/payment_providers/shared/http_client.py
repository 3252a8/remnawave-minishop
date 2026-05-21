from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from aiohttp import ClientSession, ClientTimeout

SuccessCheck = Callable[[int, Any], bool]


def http_ok(status: int, _body: Any) -> bool:
    """Default success criterion — HTTP 200 with any body."""
    return status == 200


async def post_json_request(
    session: ClientSession,
    url: str,
    *,
    body: Any,
    headers: Optional[Mapping[str, str]] = None,
    log_prefix: str,
    is_success: SuccessCheck = http_ok,
) -> Tuple[bool, Dict[str, Any]]:
    """Centralized JSON-POST every HTTP-API provider used to inline ~25 lines for.

    On transport failure, JSON decode failure, or rejected ``is_success`` check,
    returns ``(False, {"status": ..., "message": ..., "raw": ...?})`` so callers
    can decide what to do (typically: mark the payment as ``failed_creation``).
    """
    try:
        async with session.post(
            url,
            json=body,
            headers=dict(headers) if headers else None,
        ) as response:
            response_text = await response.text()
            try:
                response_data = json.loads(response_text) if response_text else {}
            except json.JSONDecodeError:
                logging.error("%s: invalid JSON response: %s", log_prefix, response_text)
                return False, {
                    "status": response.status,
                    "message": "invalid_json",
                    "raw": response_text,
                }
            if not is_success(response.status, response_data):
                logging.error(
                    "%s: API returned error (status=%s, body=%s)",
                    log_prefix,
                    response.status,
                    response_data,
                )
                return False, {"status": response.status, "message": response_data}
            return True, response_data
    except Exception as exc:
        logging.exception("%s: request failed.", log_prefix)
        return False, {"message": str(exc)}


def first_value(data: Optional[Mapping[str, Any]], *keys: str) -> Optional[str]:
    """Return the first non-empty value among ``keys`` (cast to ``str``)."""
    if not data:
        return None
    for key in keys:
        value = data.get(key)
        if value:
            return str(value)
    return None


class HttpClientMixin:
    """Shared lazy ``aiohttp.ClientSession`` lifecycle for provider services.

    Each subclass calls ``self._init_http_client(total_timeout=...)`` from
    ``__init__`` and inherits ``_get_session`` / ``close``. The session is
    created on first use and recreated transparently if it was closed.
    """

    _timeout: ClientTimeout
    _session: Optional[ClientSession]

    def _init_http_client(self, *, total_timeout: float = 20.0) -> None:
        self._timeout = ClientTimeout(total=total_timeout)
        self._session = None

    async def _get_session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            self._session = ClientSession(timeout=self._timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
