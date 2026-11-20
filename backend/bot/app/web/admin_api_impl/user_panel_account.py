from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.context import PanelService, get_optional_subscription_service, get_panel_service
from db.dal import subscription_dal, user_dal

from .common import _error


def user_panel_service(request: web.Request) -> PanelService | None:
    service = get_panel_service(request)
    if service is not None:
        return service
    subscription_service = get_optional_subscription_service(request)
    return getattr(subscription_service, "panel_service", None)


async def linked_panel_account(
    session: AsyncSession, user_id: int, *, lock: bool = False
) -> str | web.Response:
    load = user_dal.lock_user_by_id if lock else user_dal.get_user_by_id
    user = await load(session, user_id)
    if user is None:
        return _error(404, "not_found")
    reference = str(user.panel_user_uuid or "").strip()
    if not reference:
        active = await subscription_dal.get_active_subscription_by_user_id(session, user_id)
        reference = str(getattr(active, "panel_user_uuid", None) or "").strip()
    return reference or _error(404, "no_panel_user")
