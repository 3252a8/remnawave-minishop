"""QR sign-in requests: a waiting browser is approved from a session elsewhere.

The waiting browser shows a QR code that points back at this shop, so it never has
to reach Telegram. A signed-in session claims the one-time code from that QR and
then proves it is looking at the waiting screen by typing the two-digit number the
screen shows. Only the browser that started the request can collect the session,
and it can collect it once.

Lifecycle: ``pending`` -> ``scanned`` (claimed by one account) -> ``approved`` ->
``consumed``; ``pending``/``scanned`` may also end as ``denied`` or ``cancelled``,
and anything unfinished simply expires.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.auth_models import QrLoginRequest

from ._sqlalchemy import rowcount

CODE_TTL_SECONDS = 120
APPROVAL_TTL_SECONDS = 120
# After approval the waiting browser polls every couple of seconds; give it room.
COLLECT_TTL_SECONDS = 60
MAX_NUMBER_ATTEMPTS = 3
RETENTION_SECONDS = 3600

STATUS_PENDING = "pending"
STATUS_SCANNED = "scanned"
STATUS_APPROVED = "approved"
STATUS_CONSUMED = "consumed"
STATUS_DENIED = "denied"
STATUS_CANCELLED = "cancelled"

# ``secrets.token_urlsafe(16)``: 128 random bits as 22 URL-safe characters.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{22}")

PollStatus = Literal["pending", "scanned", "approved", "denied", "expired"]
ClaimError = Literal["not_found", "already_claimed"]
ApproveOutcome = Literal["approved", "wrong_number", "denied", "not_found"]


@dataclass(frozen=True)
class StartedRequest:
    request_id: str
    code: str
    expires_at: datetime


@dataclass(frozen=True)
class PollResult:
    status: PollStatus
    match_number: int | None = None
    user_id: int | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class ClaimResult:
    request: QrLoginRequest | None = None
    error: ClaimError | None = None


@dataclass(frozen=True)
class ApproveResult:
    outcome: ApproveOutcome
    attempts_left: int = 0


def is_token(value: str) -> bool:
    """Whether ``value`` has the shape of a code or request id this module issues."""
    return bool(_TOKEN_RE.fullmatch(value or ""))


def code_digest(code: str) -> str:
    return hashlib.sha256(code.encode("ascii")).hexdigest()


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _is_live(record: QrLoginRequest, now: datetime) -> bool:
    return as_utc(record.expires_at) > now


async def purge_expired(session: AsyncSession, *, now: datetime) -> None:
    """Drop requests that ended long enough ago that nobody can still poll them."""
    await session.execute(
        delete(QrLoginRequest).where(
            QrLoginRequest.expires_at < now - timedelta(seconds=RETENTION_SECONDS)
        )
    )


async def start_request(
    session: AsyncSession,
    *,
    now: datetime,
    requester_ip: str | None,
    requester_user_agent: str | None,
) -> StartedRequest:
    await purge_expired(session, now=now)
    code = secrets.token_urlsafe(16)
    record = QrLoginRequest(
        request_id=secrets.token_urlsafe(16),
        code_hash=code_digest(code),
        status=STATUS_PENDING,
        match_number=10 + secrets.randbelow(90),
        number_attempts=0,
        requester_ip=(requester_ip or "")[:64] or None,
        requester_user_agent=(requester_user_agent or "")[:255] or None,
        expires_at=now + timedelta(seconds=CODE_TTL_SECONDS),
    )
    session.add(record)
    await session.flush()
    return StartedRequest(
        request_id=str(record.request_id),
        code=code,
        expires_at=now + timedelta(seconds=CODE_TTL_SECONDS),
    )


async def poll_request(session: AsyncSession, request_id: str, *, now: datetime) -> PollResult:
    """Report progress to the waiting browser; collect the session exactly once."""
    record = await session.get(QrLoginRequest, request_id)
    if record is None:
        return PollResult("expired")
    status = str(record.status)
    if status == STATUS_DENIED:
        return PollResult("denied")
    if status in {STATUS_CONSUMED, STATUS_CANCELLED} or not _is_live(record, now):
        return PollResult("expired")
    expires_at = as_utc(record.expires_at)
    if status == STATUS_PENDING:
        return PollResult("pending", expires_at=expires_at)
    if status == STATUS_SCANNED:
        return PollResult("scanned", match_number=int(record.match_number), expires_at=expires_at)
    if status == STATUS_APPROVED and record.user_id is not None:
        user_id = int(record.user_id)
        result = await session.execute(
            update(QrLoginRequest)
            .where(
                QrLoginRequest.request_id == request_id,
                QrLoginRequest.status == STATUS_APPROVED,
            )
            .values(status=STATUS_CONSUMED, finished_at=now)
        )
        if rowcount(result) == 1:
            return PollResult("approved", user_id=user_id)
    return PollResult("expired")


async def cancel_request(session: AsyncSession, request_id: str, *, now: datetime) -> None:
    await session.execute(
        update(QrLoginRequest)
        .where(
            QrLoginRequest.request_id == request_id,
            QrLoginRequest.status.in_((STATUS_PENDING, STATUS_SCANNED, STATUS_APPROVED)),
        )
        .values(status=STATUS_CANCELLED, finished_at=now)
    )


async def claim_request(
    session: AsyncSession, code: str, *, user_id: int, now: datetime
) -> ClaimResult:
    """Bind a scanned code to the account that scanned it; nobody else can approve it."""
    digest = code_digest(code)
    result = await session.execute(
        update(QrLoginRequest)
        .where(
            QrLoginRequest.code_hash == digest,
            QrLoginRequest.status == STATUS_PENDING,
            QrLoginRequest.expires_at > now,
        )
        .values(
            status=STATUS_SCANNED,
            user_id=user_id,
            claimed_at=now,
            expires_at=now + timedelta(seconds=APPROVAL_TTL_SECONDS),
        )
        .execution_options(synchronize_session=False)
    )
    record = (
        await session.execute(select(QrLoginRequest).where(QrLoginRequest.code_hash == digest))
    ).scalar_one_or_none()
    if record is None:
        return ClaimResult(error="not_found")
    if rowcount(result) == 1:
        await session.refresh(record)
        return ClaimResult(request=record)
    if str(record.status) == STATUS_SCANNED and _is_live(record, now):
        if record.user_id is not None and int(record.user_id) == user_id:
            # The same account scanning again (a second tap, a re-opened dialog).
            return ClaimResult(request=record)
        return ClaimResult(error="already_claimed")
    return ClaimResult(error="not_found")


async def _claimed_record(
    session: AsyncSession, request_id: str, *, user_id: int, now: datetime
) -> QrLoginRequest | None:
    record = (
        await session.execute(
            select(QrLoginRequest).where(QrLoginRequest.request_id == request_id).with_for_update()
        )
    ).scalar_one_or_none()
    if (
        record is None
        or str(record.status) != STATUS_SCANNED
        or record.user_id is None
        or int(record.user_id) != user_id
        or not _is_live(record, now)
    ):
        return None
    return record


async def approve_request(
    session: AsyncSession,
    request_id: str,
    *,
    user_id: int,
    number: int,
    now: datetime,
) -> ApproveResult:
    """Approve only when the typed number matches the waiting screen.

    A wrong number costs an attempt; running out of attempts denies the request,
    so somebody who was merely sent a code cannot guess their way through.
    """
    record = await _claimed_record(session, request_id, user_id=user_id, now=now)
    if record is None:
        return ApproveResult("not_found")
    if number != int(record.match_number):
        record.number_attempts = int(record.number_attempts or 0) + 1
        attempts_left = MAX_NUMBER_ATTEMPTS - int(record.number_attempts)
        if attempts_left <= 0:
            record.status = STATUS_DENIED
            record.finished_at = now
            await session.flush()
            return ApproveResult("denied")
        await session.flush()
        return ApproveResult("wrong_number", attempts_left=attempts_left)
    record.status = STATUS_APPROVED
    record.approved_at = now
    record.expires_at = now + timedelta(seconds=COLLECT_TTL_SECONDS)
    await session.flush()
    return ApproveResult("approved")


async def deny_request(
    session: AsyncSession, request_id: str, *, user_id: int, now: datetime
) -> bool:
    record = await _claimed_record(session, request_id, user_id=user_id, now=now)
    if record is None:
        return False
    record.status = STATUS_DENIED
    record.finished_at = now
    await session.flush()
    return True
