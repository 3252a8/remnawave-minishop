"""Bounded request/job timings without SQL text, parameters or user identifiers."""

import logging
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import AsyncAdaptedQueuePool

logger = logging.getLogger(__name__)


@dataclass
class PerformanceScope:
    sql_count: int = 0
    sql_seconds: float = 0.0
    lock_wait_seconds: float = 0.0
    phases: dict[str, float] = field(default_factory=dict)
    cache: str = "none"


current_scope: ContextVar[PerformanceScope | None] = ContextVar("performance_scope", default=None)


class TimedAsyncPool(AsyncAdaptedQueuePool):
    def _do_get(self) -> Any:
        with performance_phase("pool_checkout"):
            return super()._do_get()


@asynccontextmanager
async def performance_operation(name: str) -> AsyncIterator[None]:
    scope = PerformanceScope()
    token = current_scope.set(scope)
    started = time.monotonic()
    try:
        yield
    finally:
        current_scope.reset(token)
        logger.info(
            "metric operation_seconds=%.4f operation=%s sql_count=%s sql_seconds=%.4f "
            "lock_wait_seconds=%.4f phases=%s",
            time.monotonic() - started,
            name,
            scope.sql_count,
            scope.sql_seconds,
            scope.lock_wait_seconds,
            ",".join(f"{key}:{value:.4f}" for key, value in scope.phases.items()),
        )


@contextmanager
def performance_phase(name: str) -> Iterator[None]:
    started = time.monotonic()
    try:
        yield
    finally:
        scope = current_scope.get()
        if scope is not None:
            scope.phases[name] = scope.phases.get(name, 0.0) + time.monotonic() - started


def record_cache_result(result: str) -> None:
    scope = current_scope.get()
    if scope is not None:
        scope.cache = result


def instrument_engine(engine: AsyncEngine) -> None:
    def before_execute(
        conn: Any, cursor: Any, statement: Any, parameters: Any, context: Any, many: Any
    ) -> None:
        scope = current_scope.get()
        if scope is not None:
            context._minishop_performance = (scope, time.monotonic())

    def after_execute(
        conn: Any, cursor: Any, statement: Any, parameters: Any, context: Any, many: Any
    ) -> None:
        measured = getattr(context, "_minishop_performance", None)
        if measured is not None:
            scope, started = measured
            scope.sql_count += 1
            scope.sql_seconds += time.monotonic() - started
            if context.isinsert or context.isupdate or context.isdelete:
                scope.phases["rows_written"] = scope.phases.get("rows_written", 0) + max(
                    0, cursor.rowcount
                )
            context._minishop_performance = None

    def failed_execute(exception_context: Any) -> None:
        context = exception_context.execution_context
        measured = getattr(context, "_minishop_performance", None)
        if measured is not None:
            scope, started = measured
            scope.sql_count += 1
            scope.sql_seconds += time.monotonic() - started
            context._minishop_performance = None

    def checkout(dbapi_connection: Any, record: Any, proxy: Any) -> None:
        record.info["performance_checkout"] = (current_scope.get(), time.monotonic())

    def checkin(dbapi_connection: Any, record: Any) -> None:
        measured = record.info.pop("performance_checkout", None)
        if measured is not None and measured[0] is not None:
            scope, started = measured
            elapsed = time.monotonic() - started
            scope.phases["connection_held"] = scope.phases.get("connection_held", 0) + elapsed
            scope.phases["connection_held_max"] = max(
                scope.phases.get("connection_held_max", 0), elapsed
            )

    event.listen(engine.sync_engine, "before_cursor_execute", before_execute)
    event.listen(engine.sync_engine, "after_cursor_execute", after_execute)
    event.listen(engine.sync_engine, "handle_error", failed_execute)
    event.listen(engine.sync_engine.pool, "checkout", checkout)
    event.listen(engine.sync_engine.pool, "checkin", checkin)
