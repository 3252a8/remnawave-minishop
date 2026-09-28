from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from db.dal import partner_dal, user_dal
from db.models import User

ReferralLookupSource = Literal["webapp", "telegram_start"]


class RegistrationInviteStatus(StrEnum):
    MISSING = "missing"
    INVALID = "invalid"
    SELF_REFERRAL = "self_referral"
    VALID = "valid"


class RegistrationInviteRequiredError(PermissionError):
    def __init__(self, status: RegistrationInviteStatus):
        self.status = status
        super().__init__(status.value)


@dataclass(frozen=True)
class RegistrationInviteCheck:
    enabled: bool
    status: RegistrationInviteStatus
    referrer_user_id: int | None = None
    partner_id: int | None = None
    partner_user_id: int | None = None
    partner_code: str | None = None

    @property
    def allowed(self) -> bool:
        return not self.enabled or self.status == RegistrationInviteStatus.VALID

    @property
    def requires_invite(self) -> bool:
        return self.enabled and self.status != RegistrationInviteStatus.VALID


@dataclass(frozen=True)
class _ReferralLookupResult:
    status: RegistrationInviteStatus
    referrer_user_id: int | None = None
    partner_id: int | None = None
    partner_user_id: int | None = None
    partner_code: str | None = None


def registration_invite_only_enabled(settings: Settings) -> bool:
    try:
        return bool(settings.registration_settings.invite_only_enabled)
    except AttributeError:
        return bool(settings.REGISTRATION_INVITE_ONLY_ENABLED)


def referral_program_enabled(settings: Settings) -> bool:
    try:
        return bool(settings.referral_settings.enabled)
    except AttributeError:
        return bool(settings.REFERRAL_PROGRAM_ENABLED)


def _remnashop_referral_compat_enabled(settings: Settings) -> bool:
    try:
        return bool(settings.compatibility_settings.remnashop_referral_code_compat_enabled)
    except AttributeError:
        return bool(settings.MIGRATION_REMNASHOP_REFERRAL_CODE_COMPAT_ENABLED)


def _legacy_refs_enabled(settings: Settings) -> bool:
    try:
        return bool(settings.LEGACY_REFS)
    except AttributeError:
        return True


def _partner_referral_redirect_enabled(settings: Settings) -> bool:
    try:
        config = settings.partner_settings
    except (AttributeError, ValueError):
        return False
    return bool(
        getattr(config, "enabled", False) and getattr(config, "referral_program_disabled", False)
    )


async def _resolved_referrer_result(
    session: AsyncSession,
    *,
    settings: Settings,
    referrer_user_id: int,
) -> _ReferralLookupResult:
    if not _partner_referral_redirect_enabled(settings):
        return _ReferralLookupResult(
            RegistrationInviteStatus.VALID,
            referrer_user_id=referrer_user_id,
        )

    profile = await partner_dal.get_profile_by_user_id(session, referrer_user_id)
    if profile is None:
        return _ReferralLookupResult(
            RegistrationInviteStatus.VALID,
            referrer_user_id=referrer_user_id,
        )
    if profile.status != "active" or profile.user_id is None:
        return _ReferralLookupResult(RegistrationInviteStatus.INVALID)
    return _ReferralLookupResult(
        RegistrationInviteStatus.VALID,
        partner_id=int(profile.partner_id),
        partner_user_id=int(profile.user_id),
        partner_code=str(profile.partner_code),
    )


def strip_referral_param_prefix(
    raw: str | None,
    *,
    preserve_current_u_prefix: bool,
) -> str:
    value = (raw or "").strip()
    if not value:
        return ""

    value_lower = value.lower()
    if value_lower.startswith("ref_u") and not preserve_current_u_prefix:
        value = value[5:]
    elif value_lower.startswith("ref_"):
        value = value[4:]
    return value


def normalize_webapp_referral_param(raw: str | None) -> str | None:
    value = strip_referral_param_prefix(raw, preserve_current_u_prefix=False)
    if not value:
        return None

    if value and value[0].lower() == "u" and len(value) == 10:
        value = value[1:]

    if not re.fullmatch(r"[A-Za-z0-9]{1,32}", value):
        return None
    return value.upper()


def webapp_referral_lookup_candidates(
    raw: str | None,
    *,
    remnashop_compat: bool,
) -> list[str]:
    if not remnashop_compat:
        normalized = normalize_webapp_referral_param(raw)
        return [normalized] if normalized else []

    value = strip_referral_param_prefix(raw, preserve_current_u_prefix=True)
    if not value or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value):
        return []

    candidates = [value]
    if value and value[0].lower() == "u":
        candidates.append(value[1:])
    return _unique_nonempty(candidates)


def telegram_start_referral_lookup_candidates(
    raw_ref_value: str | None,
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
    return _unique_nonempty(candidates)


def _unique_nonempty(candidates: list[str]) -> list[str]:
    unique: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip()
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


def _is_self_referrer(user: User, current_user_id: int | None) -> bool:
    return current_user_id is not None and int(user.user_id) == int(current_user_id)


async def _lookup_referrer_by_user_id(
    session: AsyncSession,
    raw_user_id: str,
    *,
    current_user_id: int | None,
) -> tuple[int | None, bool]:
    ref_user = await user_dal.get_user_by_id(session, int(raw_user_id))
    if not ref_user:
        return None, False
    if _is_self_referrer(ref_user, current_user_id):
        return None, True
    return int(ref_user.user_id), False


async def _lookup_referrer_by_code(
    session: AsyncSession,
    code: str,
    *,
    current_user_id: int | None,
    include_legacy: bool,
) -> tuple[int | None, bool]:
    ref_user = await user_dal.get_user_by_referral_code(
        session,
        code,
        include_legacy=include_legacy,
    )
    if not ref_user:
        return None, False
    if _is_self_referrer(ref_user, current_user_id):
        return None, True
    return int(ref_user.user_id), False


async def _lookup_referrer(
    session: AsyncSession,
    raw_referral_param: str | None,
    *,
    settings: Settings,
    current_user_id: int | None,
    source: ReferralLookupSource,
) -> _ReferralLookupResult:
    value = str(raw_referral_param or "").strip()
    if not value:
        return _ReferralLookupResult(RegistrationInviteStatus.MISSING)
    if not referral_program_enabled(settings):
        return _ReferralLookupResult(RegistrationInviteStatus.INVALID)

    remnashop_compat = _remnashop_referral_compat_enabled(settings)
    legacy_refs_enabled = _legacy_refs_enabled(settings)
    self_referral_seen = False

    if source == "telegram_start":
        if value.isdigit() and legacy_refs_enabled:
            referrer_id, is_self = await _lookup_referrer_by_user_id(
                session,
                value,
                current_user_id=current_user_id,
            )
            if referrer_id is not None:
                return await _resolved_referrer_result(
                    session,
                    settings=settings,
                    referrer_user_id=referrer_id,
                )
            self_referral_seen = self_referral_seen or is_self
        candidates = telegram_start_referral_lookup_candidates(
            value,
            remnashop_compat=remnashop_compat,
        )
    else:
        candidates = webapp_referral_lookup_candidates(
            value,
            remnashop_compat=remnashop_compat,
        )

    if not candidates:
        return _ReferralLookupResult(RegistrationInviteStatus.INVALID)

    for candidate in candidates:
        if (
            source == "webapp"
            and candidate.isdigit()
            and legacy_refs_enabled
            and not remnashop_compat
        ):
            referrer_id, is_self = await _lookup_referrer_by_user_id(
                session,
                candidate,
                current_user_id=current_user_id,
            )
            if referrer_id is not None:
                return await _resolved_referrer_result(
                    session,
                    settings=settings,
                    referrer_user_id=referrer_id,
                )
            self_referral_seen = self_referral_seen or is_self

        referrer_id, is_self = await _lookup_referrer_by_code(
            session,
            candidate,
            current_user_id=current_user_id,
            include_legacy=remnashop_compat,
        )
        if referrer_id is not None:
            return await _resolved_referrer_result(
                session,
                settings=settings,
                referrer_user_id=referrer_id,
            )
        self_referral_seen = self_referral_seen or is_self

        if source == "webapp" and candidate.isdigit() and legacy_refs_enabled and remnashop_compat:
            referrer_id, is_self = await _lookup_referrer_by_user_id(
                session,
                candidate,
                current_user_id=current_user_id,
            )
            if referrer_id is not None:
                return await _resolved_referrer_result(
                    session,
                    settings=settings,
                    referrer_user_id=referrer_id,
                )
            self_referral_seen = self_referral_seen or is_self

    if self_referral_seen:
        return _ReferralLookupResult(RegistrationInviteStatus.SELF_REFERRAL)
    return _ReferralLookupResult(RegistrationInviteStatus.INVALID)


async def resolve_referrer_user_id(
    session: AsyncSession,
    raw_referral_param: str | None,
    *,
    settings: Settings,
    current_user_id: int | None,
    source: ReferralLookupSource = "webapp",
) -> int | None:
    lookup = await _lookup_referrer(
        session,
        raw_referral_param,
        settings=settings,
        current_user_id=current_user_id,
        source=source,
    )
    return lookup.referrer_user_id


async def evaluate_registration_invite(
    session: AsyncSession,
    raw_referral_param: str | None,
    *,
    settings: Settings,
    current_user_id: int | None,
    source: ReferralLookupSource = "webapp",
) -> RegistrationInviteCheck:
    raw_value = str(raw_referral_param or "").strip()
    if raw_value == "ambiguous_invite":
        return RegistrationInviteCheck(
            enabled=True,
            status=RegistrationInviteStatus.INVALID,
        )
    if raw_value.lower().startswith("p_"):
        code = raw_value[2:]
        profile = None
        try:
            partner_enabled = bool(settings.partner_settings.enabled)
        except (AttributeError, ValueError):
            partner_enabled = False
        if partner_enabled and re.fullmatch(r"[A-Za-z0-9_-]{8,64}", code):
            profile = await partner_dal.get_profile_by_code(session, code)
        partner_id: int | None = None
        partner_user_id: int | None = None
        partner_code: str | None = None
        if not profile or profile.status != "active" or profile.user_id is None:
            status = RegistrationInviteStatus.INVALID
        elif current_user_id is not None and int(profile.user_id) == int(current_user_id):
            status = RegistrationInviteStatus.SELF_REFERRAL
        else:
            status = RegistrationInviteStatus.VALID
            partner_id = int(profile.partner_id)
            partner_user_id = int(profile.user_id)
            partner_code = str(profile.partner_code)
        return RegistrationInviteCheck(
            enabled=registration_invite_only_enabled(settings),
            status=status,
            partner_id=partner_id,
            partner_user_id=partner_user_id,
            partner_code=partner_code,
        )
    lookup = await _lookup_referrer(
        session,
        raw_referral_param,
        settings=settings,
        current_user_id=current_user_id,
        source=source,
    )
    return RegistrationInviteCheck(
        enabled=registration_invite_only_enabled(settings),
        status=lookup.status,
        referrer_user_id=lookup.referrer_user_id,
        partner_id=lookup.partner_id,
        partner_user_id=lookup.partner_user_id,
        partner_code=lookup.partner_code,
    )
