from typing import Optional

from aiogram import Router
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from db.dal import user_dal
from db.models import User

router = Router(name="user_start_router")


def _remnashop_referral_compat_enabled(settings: Settings) -> bool:
    return bool(settings.MIGRATION_REMNASHOP_REFERRAL_CODE_COMPAT_ENABLED)


def _referral_code_lookup_candidates(
    raw_ref_value: str,
    *,
    remnashop_compat: bool,
) -> list[str]:
    value = str(raw_ref_value or "").strip()
    if not value:
        return []

    candidates = [value]
    if value and value[0].lower() == "u":
        stripped_current_prefix = value[1:]
        if remnashop_compat:
            candidates.append(stripped_current_prefix)
        else:
            candidates = [stripped_current_prefix]

    unique: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip()
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


async def _resolve_referrer_from_start_ref(
    session: AsyncSession,
    raw_ref_value: str,
    *,
    settings: Settings,
    current_user_id: int,
) -> Optional[int]:
    ref_user: Optional[User] = None
    if raw_ref_value.isdigit() and settings.LEGACY_REFS:
        potential_referrer_id = int(raw_ref_value)
        if potential_referrer_id != current_user_id:
            ref_user = await user_dal.get_user_by_id(session, potential_referrer_id)

    include_legacy = _remnashop_referral_compat_enabled(settings)
    if not ref_user:
        for code in _referral_code_lookup_candidates(
            raw_ref_value,
            remnashop_compat=include_legacy,
        ):
            ref_user = await user_dal.get_user_by_referral_code(
                session,
                code,
                include_legacy=include_legacy,
            )
            if ref_user:
                break

    if ref_user and ref_user.user_id != current_user_id:
        return int(ref_user.user_id)
    return None
