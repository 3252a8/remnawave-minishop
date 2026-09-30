"""The same persistent failure budget applies to every code lookup."""

from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from db.dal import security_dal


async def check_code_attempt(
    session: AsyncSession, settings: Settings, user_id: int, *, failed: bool = False
) -> security_dal.ThrottleDecision:
    arguments = {"scope": security_dal.PROMO_CODE_APPLY_SCOPE, "identifier": f"user:{int(user_id)}"}
    if failed:
        return await security_dal.record_throttle_failure(
            session,
            **arguments,
            max_failures=settings.BRUTE_FORCE_MAX_FAILURES,
            window_seconds=settings.BRUTE_FORCE_WINDOW_SECONDS,
            lock_seconds=settings.BRUTE_FORCE_LOCK_SECONDS,
        )
    return await security_dal.check_throttle(session, **arguments)
