from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from config.tariffs_config import Tariff, TariffsConfig, normalize_tariff_access_code
from db.dal import subscription_dal

TARIFF_ACCESS_HEADER = "X-Tariff-Access-Code"


def request_tariff_access_code(request: Any) -> str | None:
    path_code = str(getattr(request, "match_info", {}).get("tariff_access_code") or "")
    header_code = str(getattr(request, "headers", {}).get(TARIFF_ACCESS_HEADER) or "")
    return normalize_tariff_access_code(path_code) or normalize_tariff_access_code(header_code)


async def require_user_available_tariff(
    session: AsyncSession,
    config: TariffsConfig,
    *,
    user_id: int,
    tariff_key: str,
    panel_user_uuid: str | None = None,
    access_code: str | None = None,
) -> Tariff:
    """Allow a hidden tariff when assigned or unlocked by its exact access code."""
    try:
        return config.require(tariff_key)
    except KeyError:
        if access_code:
            try:
                return config.require_for_user(tariff_key, None, access_code)
            except KeyError:
                pass
        subscription = await subscription_dal.get_active_subscription_by_user_id(
            session,
            user_id,
            panel_user_uuid,
        )
        if subscription is None:
            subscription = await subscription_dal.get_latest_subscription_by_user_id(
                session,
                user_id,
                panel_user_uuid,
            )
        return config.require_for_user(
            tariff_key,
            str(getattr(subscription, "tariff_key", "") or ""),
            access_code,
        )
