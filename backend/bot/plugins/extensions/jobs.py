"""Transactional outbox and leased at-least-once work, shared by extensions."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import JsonValue, TypeAdapter
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.plugins.packages import generation_is_current
from db.extension_models import ExtensionOperation

from .contracts import ExtensionError, OperationContext
from .registry import get_registry, split_key

if TYPE_CHECKING:
    from bot.plugins.spec import PluginContext

logger = logging.getLogger(__name__)
JSON_OBJECT = TypeAdapter(dict[str, JsonValue])


def json_object(value: dict[str, JsonValue]) -> str:
    body = json.dumps(
        JSON_OBJECT.validate_python(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    if len(body.encode("utf-8")) > 262144:
        raise ExtensionError("extension_payload_too_large", 400)
    return body


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def enqueue(
    session: AsyncSession,
    *,
    job: str,
    idempotency_key: str,
    payload: dict[str, JsonValue],
    user_id: int | None = None,
    not_before: datetime | None = None,
) -> ExtensionOperation:
    """Join the caller's transaction; never commit. Reusing a key with new input fails."""
    owner, name = split_key(job)
    entry = get_registry().require(owner)
    handler = next((item for item in entry.contributions.jobs if item.id == name), None)
    if handler is None:
        raise ExtensionError("extension_job_unavailable", 404)
    return await enqueue_internal(
        session,
        owner=owner,
        kind=name,
        idempotency_key=idempotency_key,
        payload=payload,
        user_id=user_id,
        not_before=not_before,
        max_attempts=handler.max_attempts,
    )


async def enqueue_internal(
    session: AsyncSession,
    *,
    owner: str,
    kind: str,
    idempotency_key: str,
    payload: dict[str, JsonValue],
    user_id: int | None = None,
    not_before: datetime | None = None,
    max_attempts: int = 10,
) -> ExtensionOperation:
    if not 1 <= len(idempotency_key) <= 128:
        raise ExtensionError("invalid_extension_idempotency_key", 400)
    body = json_object(payload)
    query = select(ExtensionOperation).where(
        ExtensionOperation.owner == owner,
        ExtensionOperation.kind == kind,
        ExtensionOperation.idempotency_key == idempotency_key,
    )
    existing = await session.scalar(query)
    if existing is None:
        now = datetime.now(UTC)
        row = ExtensionOperation(
            id=uuid.uuid4().hex,
            owner=owner,
            kind=kind,
            user_id=user_id,
            idempotency_key=idempotency_key,
            payload_json=body,
            state="queued",
            attempts=0,
            max_attempts=max_attempts,
            not_before=utc(not_before or now),
            created_at=now,
            updated_at=now,
        )
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
            return row
        except IntegrityError:
            existing = await session.scalar(query)
            if existing is None:
                raise
    if existing.payload_json != body or existing.user_id != user_id:
        raise ExtensionError("extension_idempotency_conflict")
    return existing


async def publish(
    session: AsyncSession,
    *,
    event: str,
    event_id: str,
    payload: dict[str, JsonValue],
    user_id: int | None = None,
) -> None:
    """Persist one delivery per subscriber in the same transaction as the domain change."""
    if not event_id or len(event_id) > 256:
        raise ExtensionError("invalid_extension_event_id", 400)
    for owner, entry in get_registry().owners().items():
        for subscription in entry.contributions.events:
            if subscription.event != event:
                continue
            key = hashlib.sha256(f"{event}:{event_id}".encode()).hexdigest()
            await enqueue(
                session,
                job=f"{owner}:{subscription.job}",
                idempotency_key=key,
                payload={"event": event, "event_id": event_id, "payload": payload},
                user_id=user_id,
            )


async def _schedules(ctx: PluginContext) -> None:
    now = datetime.now(UTC)
    async with ctx.require_session_factory()() as session:
        for owner, entry in get_registry().owners().items():
            for job in entry.contributions.jobs:
                if job.interval_seconds is None:
                    continue
                slot = int(now.timestamp()) // job.interval_seconds
                await enqueue(
                    session,
                    job=f"{owner}:{job.id}",
                    idempotency_key=f"schedule:{slot}",
                    payload={"slot": slot},
                )
        await session.commit()


async def run_once(ctx: PluginContext) -> bool:
    """Claim with a fenced lease. Handlers run without a long database transaction."""
    if not generation_is_current():
        return False
    now = datetime.now(UTC)
    async with ctx.require_session_factory()() as session:
        row = await session.scalar(
            select(ExtensionOperation)
            .where(
                or_(
                    and_(
                        ExtensionOperation.state.in_(("queued", "blocked")),
                        ExtensionOperation.not_before <= now,
                    ),
                    and_(
                        ExtensionOperation.state == "running", ExtensionOperation.lease_until <= now
                    ),
                )
            )
            .order_by(ExtensionOperation.not_before, ExtensionOperation.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            return False
        entry = get_registry().owners().get(str(row.owner))
        handler = (
            next((item for item in entry.contributions.jobs if item.id == row.kind), None)
            if entry
            else None
        )
        internal = row.kind in {"_fulfill", "_revoke", "_reward", "_backup_upload"}
        if entry is None or (handler is None and not internal):
            row.state = "blocked"
            row.error_code = "extension_unavailable"
            row.not_before = now + timedelta(seconds=60)
            row.lease_token = row.lease_until = None
            await session.commit()
            return True
        if int(row.attempts) >= int(row.max_attempts):
            row.state = "failed"
            row.error_code = "extension_attempts_exhausted"
            await session.commit()
            return True
        timeout = (
            handler.timeout_seconds if handler else (600 if row.kind == "_backup_upload" else 120)
        )
        token = uuid.uuid4().hex
        row.lease_token = token
        row.lease_until = now + timedelta(seconds=timeout + 30)
        row.state = "running"
        row.attempts = int(row.attempts) + 1
        row.updated_at = now
        operation = OperationContext(str(row.id), str(row.owner), row.user_id, ctx, token)
        payload = JSON_OBJECT.validate_json(str(row.payload_json))
        await session.commit()
    state = "succeeded"
    error: str | None = None
    result: dict[str, JsonValue] = {}
    try:
        operation.assert_current()
        async with asyncio.timeout(timeout):
            if internal:
                from .operations import execute_operation

                result = await execute_operation(operation, str(row.kind), payload)
            elif handler is not None:
                result = await handler.run(operation, payload)
        encoded_result = json_object(result)
    except Exception as exc:
        error = exc.code if isinstance(exc, ExtensionError) else "extension_operation_failed"
        state = (
            "blocked" if isinstance(exc, ExtensionError) and exc.status in {409, 503} else "queued"
        )
        encoded_result = None
        # Exceptions can contain external credentials; persist/log a stable code only.
        logger.warning("Extension operation %s: %s", operation.operation_id, error)
    async with ctx.require_session_factory()() as session:
        current = await session.scalar(
            select(ExtensionOperation)
            .where(ExtensionOperation.id == operation.operation_id)
            .with_for_update()
        )
        if current is None or current.lease_token != token:
            return True
        current.state = state
        current.error_code = error
        if encoded_result is not None:
            current.result_json = encoded_result
        current.updated_at = datetime.now(UTC)
        current.not_before = current.updated_at + timedelta(
            seconds=min(3600, 2 ** min(int(current.attempts), 12))
        )
        current.lease_token = current.lease_until = None
        if state == "blocked":
            current.attempts = max(0, int(current.attempts) - 1)
            current.not_before = current.updated_at + timedelta(seconds=60)
        elif state == "queued" and int(current.attempts) >= int(current.max_attempts):
            current.state = "failed"
        await session.commit()
    if state == "succeeded" and row.kind == "_backup_upload":
        from .backups import upload_path

        try:
            upload_path(ctx, operation.owner, payload).unlink(missing_ok=True)
        except OSError:
            logger.warning("Extension upload cleanup failed: %s", operation.operation_id)
    return True


async def run_worker(ctx: PluginContext) -> None:
    last_schedule = 0.0
    while generation_is_current():
        try:
            now = asyncio.get_running_loop().time()
            if now - last_schedule >= 30:
                await _schedules(ctx)
                last_schedule = now
            if await run_once(ctx):
                continue
        except Exception:
            logger.error("Extension worker database operation failed")
        await asyncio.sleep(2)
