from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import case, delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import SecurityThrottle

EMAIL_CODE_VERIFY_SCOPE = "email_code_verify"
PROMO_CODE_APPLY_SCOPE = "promo_code_apply"


@dataclass(frozen=True)
class ThrottleDecision:
    locked: bool
    retry_after: Optional[int] = None


def _utc_now(value: Optional[datetime] = None) -> datetime:
    if value is None:
        value = datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _retry_after_seconds(locked_until: Optional[datetime], now: datetime) -> Optional[int]:
    if not locked_until:
        return None
    locked_until = _utc_now(locked_until)
    remaining = int((locked_until - now).total_seconds())
    return max(1, remaining) if remaining > 0 else None


async def get_throttle_state(
    session: AsyncSession,
    *,
    scope: str,
    identifier: str,
) -> Optional[SecurityThrottle]:
    stmt = (
        select(SecurityThrottle)
        .where(
            SecurityThrottle.scope == scope,
            SecurityThrottle.identifier == identifier,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def check_throttle(
    session: AsyncSession,
    *,
    scope: str,
    identifier: str,
    now: Optional[datetime] = None,
) -> ThrottleDecision:
    now = _utc_now(now)
    row = await get_throttle_state(session, scope=scope, identifier=identifier)
    if not row or not row.locked_until:
        return ThrottleDecision(locked=False)

    locked_until = _utc_now(row.locked_until)
    if locked_until <= now:
        return ThrottleDecision(locked=False)

    return ThrottleDecision(
        locked=True,
        retry_after=_retry_after_seconds(locked_until, now),
    )


async def record_throttle_failure(
    session: AsyncSession,
    *,
    scope: str,
    identifier: str,
    max_failures: int,
    window_seconds: int,
    lock_seconds: int,
    now: Optional[datetime] = None,
) -> ThrottleDecision:
    now = _utc_now(now)
    max_failures = max(1, int(max_failures))
    window_seconds = max(1, int(window_seconds))
    lock_seconds = max(1, int(lock_seconds))
    window_cutoff = now - timedelta(seconds=window_seconds)
    lock_until = now + timedelta(seconds=lock_seconds)

    failure_count_expr = case(
        (
            or_(
                SecurityThrottle.window_started_at.is_(None),
                SecurityThrottle.window_started_at <= window_cutoff,
            ),
            1,
        ),
        else_=SecurityThrottle.failures + 1,
    )

    stmt = (
        pg_insert(SecurityThrottle)
        .values(
            scope=scope,
            identifier=identifier,
            failures=1,
            window_started_at=now,
            last_attempt_at=now,
            locked_until=lock_until if max_failures <= 1 else None,
        )
        .on_conflict_do_update(
            index_elements=[SecurityThrottle.scope, SecurityThrottle.identifier],
            set_={
                "failures": failure_count_expr,
                "window_started_at": case(
                    (
                        or_(
                            SecurityThrottle.window_started_at.is_(None),
                            SecurityThrottle.window_started_at <= window_cutoff,
                        ),
                        now,
                    ),
                    else_=SecurityThrottle.window_started_at,
                ),
                "last_attempt_at": now,
                "locked_until": case(
                    (failure_count_expr >= max_failures, lock_until),
                    else_=None,
                ),
            },
        )
        .returning(SecurityThrottle.locked_until)
    )

    result = await session.execute(stmt)
    locked_until = result.scalar_one_or_none()
    locked_until = _utc_now(locked_until) if locked_until else None
    if locked_until and locked_until > now:
        return ThrottleDecision(
            locked=True,
            retry_after=_retry_after_seconds(locked_until, now),
        )
    return ThrottleDecision(locked=False)


async def clear_throttle_state(
    session: AsyncSession,
    *,
    scope: str,
    identifier: str,
) -> None:
    stmt = delete(SecurityThrottle).where(
        SecurityThrottle.scope == scope,
        SecurityThrottle.identifier == identifier,
    )
    await session.execute(stmt)
