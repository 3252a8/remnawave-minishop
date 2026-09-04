from sqlalchemy.ext.asyncio import AsyncSession

from config.tariffs_config import Tariff, TariffsConfig
from db.dal import subscription_dal


async def require_user_available_tariff(
    session: AsyncSession,
    config: TariffsConfig,
    *,
    user_id: int,
    tariff_key: str,
    panel_user_uuid: str | None = None,
) -> Tariff:
    """Allow a hidden tariff only while it is the user's currently assigned tariff."""
    try:
        return config.require(tariff_key)
    except KeyError:
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
        )
