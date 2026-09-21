"""Fresh public-token authorization shared by the page and raw gateway."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import get_session_factory
from db.dal import subscription_dal

from .guides_panel_config import _panel_service_from_app, _panel_short_uuid_from_user


def _local_subscription_is_publicly_active(subscription: Any) -> bool:
    end_date = getattr(subscription, "end_date", None)
    if end_date and end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=UTC)
    return bool(
        getattr(subscription, "is_active", False) and end_date and end_date > datetime.now(UTC)
    )


class PanelLookupUnavailable(Exception):
    """A panel lookup failed without proving that the user was removed."""


@dataclass(frozen=True)
class SubscriptionAccess:
    token: str
    panel_user_uuid: str
    panel_short_uuid: str
    panel_url: str
    username: str


async def resolve_subscription_access(
    request: web.Request, share_token: str
) -> SubscriptionAccess | None:
    token = subscription_dal.normalize_install_share_token(share_token)
    if not token:
        return None
    factory: sessionmaker = get_session_factory(request)
    async with factory() as session:
        subscription = await subscription_dal.get_subscription_by_install_share_token(
            session, token
        )
        if subscription is None or not _local_subscription_is_publicly_active(subscription):
            return None
        panel_user_uuid = str(getattr(subscription, "panel_user_uuid", "") or "").strip()
        bound_short_uuid = str(
            getattr(subscription, "install_share_panel_short_uuid", "") or ""
        ).strip()
    if not panel_user_uuid or not bound_short_uuid:
        return None
    panel_service = _panel_service_from_app(request.app)
    if panel_service is None:
        raise PanelLookupUnavailable
    lookup = getattr(panel_service, "get_user_by_uuid_lookup", None)
    try:
        if callable(lookup):
            result = await lookup(panel_user_uuid)
            if result.get("not_found"):
                return None
            if not result.get("ok"):
                raise PanelLookupUnavailable
            panel_user = result.get("user")
        else:
            panel_user = await panel_service.get_user_by_uuid(panel_user_uuid, use_cache=False)
    except PanelLookupUnavailable:
        raise
    except Exception as exc:
        raise PanelLookupUnavailable from exc
    if not isinstance(panel_user, dict):
        raise PanelLookupUnavailable
    short_uuid = _panel_short_uuid_from_user(panel_user)
    if not short_uuid or short_uuid != bound_short_uuid:
        return None
    panel_url = str(panel_user.get("subscriptionUrl") or "").strip()
    if not panel_url:
        return None
    return SubscriptionAccess(
        token=token,
        panel_user_uuid=panel_user_uuid,
        panel_short_uuid=short_uuid,
        panel_url=panel_url,
        username=str(panel_user.get("username") or "").strip(),
    )
