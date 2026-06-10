from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Mapping, Optional, Set, Tuple, Union

from aiohttp import ClientError, ClientSession, ClientTimeout, TraceConfig

SuccessCheck = Callable[[int, Any], bool]
TimeoutSource = Union[float, Callable[[], float]]
_TRANSPORT_ATTEMPTS = 2
_DEFAULT_TIMEOUT_SECONDS = 20.0


def http_ok(status: int, _body: Any) -> bool:
    """Default success criterion — HTTP 200 with any body."""
    return status == 200


def _trace_request_ctx(trace_config_ctx: Any) -> Optional[dict]:
    ctx = getattr(trace_config_ctx, "trace_request_ctx", None)
    return ctx if isinstance(ctx, dict) else None


async def _mark_request_headers_sent(session, trace_config_ctx, params) -> None:
    ctx = _trace_request_ctx(trace_config_ctx)
    if ctx is not None:
        ctx["headers_sent"] = True


def _payment_trace_config() -> TraceConfig:
    trace_config = TraceConfig()
    trace_config.on_request_headers_sent.append(_mark_request_headers_sent)
    return trace_config


def _should_retry_transport_error(exc: Exception, trace_ctx: Mapping[str, Any]) -> bool:
    if trace_ctx.get("headers_sent"):
        return False
    return isinstance(exc, (asyncio.TimeoutError, ClientError, OSError))


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
    for attempt in range(1, _TRANSPORT_ATTEMPTS + 1):
        trace_ctx: dict[str, Any] = {"headers_sent": False}
        try:
            async with session.post(
                url,
                json=body,
                headers=dict(headers) if headers else None,
                trace_request_ctx=trace_ctx,
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
            if attempt < _TRANSPORT_ATTEMPTS and _should_retry_transport_error(exc, trace_ctx):
                logging.warning(
                    "%s: transport failed before request headers were sent; retrying (%s/%s): %s",  # noqa: E501
                    log_prefix,
                    attempt + 1,
                    _TRANSPORT_ATTEMPTS,
                    exc,
                )
                continue
            logging.exception("%s: request failed.", log_prefix)
            return False, {"message": str(exc)}
    return False, {"message": "request_failed"}


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

    ``total_timeout`` may be a callable so the timeout follows runtime
    settings changes (admin overrides apply in-process without a restart).
    When the value changes, the next request gets a fresh session; the old
    session stays open until its own in-flight requests cannot outlive it.

    Provider API calls are traced so callers can retry transport failures only
    when aiohttp has not sent request headers yet.
    """

    _timeout_source: TimeoutSource
    _session: Optional[ClientSession]
    _stale_sessions: List[ClientSession]
    _session_cleanup_tasks: Set["asyncio.Task[None]"]

    def _init_http_client(self, *, total_timeout: TimeoutSource = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout_source = total_timeout
        self._session = None
        self._stale_sessions = []
        self._session_cleanup_tasks = set()

    def _current_timeout_seconds(self) -> float:
        source = self._timeout_source
        try:
            seconds = float(source() if callable(source) else source)
        except Exception:
            return _DEFAULT_TIMEOUT_SECONDS
        return seconds if seconds > 0 else _DEFAULT_TIMEOUT_SECONDS

    async def _get_session(self) -> ClientSession:
        timeout_seconds = self._current_timeout_seconds()
        session = self._session
        if session is not None and not session.closed and session.timeout.total != timeout_seconds:
            self._session = None
            self._stale_sessions.append(session)
            task = asyncio.create_task(self._close_stale_session(session))
            self._session_cleanup_tasks.add(task)
            task.add_done_callback(self._session_cleanup_tasks.discard)
            session = None
        if session is None or session.closed:
            session = ClientSession(
                timeout=ClientTimeout(total=timeout_seconds),
                trace_configs=[_payment_trace_config()],
            )
            self._session = session
        return session

    async def _close_stale_session(self, session: ClientSession) -> None:
        # Any request started on this session is bound by its total timeout,
        # so after that long it is safe to close without cutting one off.
        await asyncio.sleep((session.timeout.total or _DEFAULT_TIMEOUT_SECONDS) + 1.0)
        if session in self._stale_sessions:
            self._stale_sessions.remove(session)
        if not session.closed:
            await session.close()

    async def close(self) -> None:
        for task in list(self._session_cleanup_tasks):
            task.cancel()
        self._session_cleanup_tasks.clear()
        sessions = [self._session, *self._stale_sessions]
        self._session = None
        self._stale_sessions = []
        for session in sessions:
            if session and not session.closed:
                await session.close()
