from bot.app.web.context import (
    get_bot,
    get_bot_username,
    get_i18n,
    get_session_factory,
    get_settings,
)
from bot.services.telegram_notifications import (
    TELEGRAM_NOTIFICATIONS_ENABLED,
    probe_telegram_notifications,
    telegram_notifications_start_link,
)

from ._runtime import (
    Any,
    Dict,
    Settings,
    json_response,
    logger,
    sessionmaker,
    user_dal,
    web,
)
from .common import (
    _invalidate_webapp_user_caches,
    _json_error,
    _require_user_id,
)


async def _probe_telegram_notifications_for_user_id(
    request: web.Request,
    user_id: int,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    settings: Settings = get_settings(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        try:
            db_user = await user_dal.get_user_by_id(session, user_id)
            if not db_user or db_user.is_banned:
                await session.rollback()
                return {
                    "ok": False,
                    "status": "access_denied",
                    "enabled": False,
                    "start_link": telegram_notifications_start_link(get_bot_username(request)),
                }
            result = await probe_telegram_notifications(
                session=session,
                bot=get_bot(request),
                settings=settings,
                i18n=get_i18n(request),
                user=db_user,
                bot_username=get_bot_username(request),
                force=force,
            )
            await session.commit()
            status = str(result.get("status") or "")
            await _invalidate_webapp_user_caches(settings, int(db_user.user_id))
            return {
                "ok": bool(result.get("ok")),
                "status": status,
                "enabled": status == TELEGRAM_NOTIFICATIONS_ENABLED,
                "start_link": result.get("start_link"),
            }
        except Exception:
            await session.rollback()
            logger.exception("Telegram notification probe failed")
            return {
                "ok": False,
                "status": "unknown",
                "enabled": False,
                "start_link": telegram_notifications_start_link(get_bot_username(request)),
            }


async def account_telegram_notifications_probe_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    force = True
    result = await _probe_telegram_notifications_for_user_id(request, user_id, force=force)
    if result.get("status") == "access_denied":
        return _json_error(403, "access_denied", "Access denied")
    return json_response({"ok": True, "telegram_notifications": result})
