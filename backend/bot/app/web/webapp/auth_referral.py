from bot.infra import events
from bot.infra.event_payloads import ReferralBonusGrantedPayload

from ._runtime import (
    Any,
    AsyncSession,
    Dict,
    Optional,
    Settings,
    SubscriptionService,
    User,
    datetime,
    logger,
    sanitize_display_name,
    sanitize_username,
    sessionmaker,
    timezone,
    user_dal,
    web,
)
from .assets import (
    _enforce_webapp_rate_limit,
)
from .auth_common import (
    _referral_param_lookup_candidates,
    _referral_welcome_telegram_required_reason,
    _remnashop_referral_compat_enabled,
    _telegram_photo_url_value,
)
from .common import (
    _invalidate_webapp_user_caches,
    _json_error,
    _normalize_language,
    _require_user_id,
)


async def _resolve_referrer_id(
    session: AsyncSession,
    raw_referral_param: Optional[str],
    *,
    current_user_id: Optional[int],
    settings: Optional[Settings] = None,
) -> Optional[int]:
    remnashop_compat = _remnashop_referral_compat_enabled(settings)
    candidates = _referral_param_lookup_candidates(
        raw_referral_param,
        remnashop_compat=remnashop_compat,
    )
    if not candidates:
        return None

    for normalized in candidates:
        ref_user = None
        if normalized.isdigit() and not remnashop_compat:
            ref_user = await user_dal.get_user_by_id(session, int(normalized))
        if not ref_user:
            ref_user = await user_dal.get_user_by_referral_code(
                session,
                normalized,
                include_legacy=remnashop_compat,
            )
        if not ref_user and normalized.isdigit() and remnashop_compat:
            ref_user = await user_dal.get_user_by_id(session, int(normalized))
        if not ref_user:
            continue
        if current_user_id is not None and int(ref_user.user_id) == int(current_user_id):
            continue
        return int(ref_user.user_id)

    return None


async def _apply_referral_to_existing_user(
    request: web.Request,
    session: AsyncSession,
    user: User,
    raw_referral_param: Optional[str],
) -> bool:
    if not raw_referral_param or user.referred_by_id is not None:
        return False

    referred_by_id = await _resolve_referrer_id(
        session,
        raw_referral_param,
        current_user_id=int(user.user_id),
        settings=request.app["settings"],
    )
    if not referred_by_id:
        return False

    subscription_service: SubscriptionService = request.app["subscription_service"]
    try:
        is_active_now = await subscription_service.has_active_subscription(
            session,
            int(user.user_id),
        )
    except Exception:
        is_active_now = False
    if is_active_now:
        return False

    user.referred_by_id = referred_by_id
    await session.flush()
    return True


async def _apply_referral_welcome_bonus_if_needed(
    request: web.Request,
    session: AsyncSession,
    user: User,
    raw_referral_param: Optional[str],
) -> Optional[datetime]:
    if not raw_referral_param or not user.referred_by_id:
        return None

    settings: Settings = request.app["settings"]
    if _referral_welcome_telegram_required_reason(settings, user):
        return None

    return await _grant_referral_welcome_bonus_if_eligible(request, session, user)


async def _grant_referral_welcome_bonus_if_eligible(
    request: web.Request,
    session: AsyncSession,
    user: User,
) -> Optional[datetime]:
    if not user.referred_by_id:
        return None

    # One-time grant: once a user has claimed the welcome bonus, never grant it
    # again. Without this marker the bonus could be re-claimed every time the
    # previous grant expired (has_active_subscription alone is not enough).
    if getattr(user, "referral_welcome_bonus_claimed_at", None) is not None:
        return None

    settings: Settings = request.app["settings"]
    referral_welcome_days = max(
        0,
        int(getattr(settings, "REFERRAL_WELCOME_BONUS_DAYS", 0) or 0),
    )
    if referral_welcome_days <= 0:
        return None

    subscription_service: SubscriptionService = request.app["subscription_service"]
    default_tariff_key = None
    tariffs_config = getattr(settings, "tariffs_config", None)
    if tariffs_config:
        default_tariff_key = getattr(tariffs_config, "default_tariff", None)
    try:
        if await subscription_service.has_active_subscription(session, int(user.user_id)):
            return None
    except Exception:
        pass

    end_date = await subscription_service.extend_active_subscription_days(
        session,
        int(user.user_id),
        referral_welcome_days,
        reason="referral_welcome_bonus",
        tariff_key=default_tariff_key,
    )
    if end_date:
        # Persisted together with the grant on the caller's commit (the extend
        # call does not commit on its own), so the bonus and its claimed-marker
        # stay atomic.
        user.referral_welcome_bonus_claimed_at = datetime.now(timezone.utc)
        await events.emit_model(
            ReferralBonusGrantedPayload(
                referee_user_id=int(user.user_id),
                referee_bonus_days=referral_welcome_days,
                referee_new_end_date=end_date,
                inviter_bonus_applied=False,
                payment_db_id=None,
                reason="welcome",
            ),
            exclude_unset=True,
        )
    return end_date


def _webapp_datetime_text(value: Optional[datetime]) -> Optional[str]:
    if not value:
        return None
    normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized.strftime("%d.%m.%Y %H:%M")


async def referral_welcome_bonus_claim_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    rate_limit_response = await _enforce_webapp_rate_limit(
        request,
        user_id=user_id,
        action="referral_welcome_claim",
    )
    if rate_limit_response:
        return rate_limit_response

    settings: Settings = request.app["settings"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        try:
            db_user = await user_dal.get_user_by_id(session, user_id)
            if not db_user or db_user.is_banned:
                await session.rollback()
                return _json_error(403, "access_denied", "Access denied")

            reason = _referral_welcome_telegram_required_reason(settings, db_user)
            if reason:
                await session.rollback()
                return _json_error(400, "referral_welcome_telegram_required", reason)

            end_date = await _grant_referral_welcome_bonus_if_eligible(
                request,
                session,
                db_user,
            )
            if not end_date:
                await session.rollback()
                return _json_error(
                    400,
                    "referral_welcome_unavailable",
                    "Referral welcome bonus is not available",
                )

            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Referral welcome bonus claim failed")
            return _json_error(500, "referral_welcome_failed", "Referral welcome bonus failed")

    await _invalidate_webapp_user_caches(settings, user_id, include_devices=True)
    return web.json_response(
        {
            "ok": True,
            "claimed": True,
            "end_date": end_date.isoformat() if isinstance(end_date, datetime) else None,
            "end_date_text": _webapp_datetime_text(end_date),
        }
    )


async def _ensure_user_from_telegram(
    session: AsyncSession,
    telegram_user: Dict[str, Any],
    settings: Settings,
    *,
    referral_param: Optional[str] = None,
) -> User:
    user_id = int(telegram_user["id"])
    telegram_language_code = _normalize_language(
        telegram_user.get("language_code") or settings.DEFAULT_LANGUAGE
    )

    profile_data = {
        "telegram_id": user_id,
        "username": sanitize_username(telegram_user.get("username")),
        "first_name": sanitize_display_name(telegram_user.get("first_name")),
        "last_name": sanitize_display_name(telegram_user.get("last_name")),
    }
    telegram_photo_url = _telegram_photo_url_value(telegram_user)
    if telegram_photo_url:
        profile_data["telegram_photo_url"] = telegram_photo_url

    db_user = await user_dal.get_user_by_telegram_id(session, user_id)
    if not db_user:
        db_user = await user_dal.get_user_by_id(session, user_id)
    if not db_user:
        referred_by_id = await _resolve_referrer_id(
            session,
            referral_param or telegram_user.get("start_param"),
            current_user_id=user_id,
            settings=settings,
        )
        db_user, created = await user_dal.create_user(
            session,
            {
                "user_id": user_id,
                **profile_data,
                "language_code": telegram_language_code,
                "referred_by_id": referred_by_id,
                "registration_date": datetime.now(timezone.utc),
            },
        )
        setattr(db_user, "_webapp_created", bool(created))
        return db_user

    update_data = {
        **profile_data,
        "language_code": _normalize_language(db_user.language_code or telegram_language_code),
    }
    changed = {key: value for key, value in update_data.items() if getattr(db_user, key) != value}
    if changed:
        db_user = await user_dal.update_user(session, db_user.user_id, changed) or db_user
    return db_user
