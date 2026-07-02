import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PanelSyncStatus

SINGLETON_ID = 1


async def get_panel_sync_status(session: AsyncSession) -> PanelSyncStatus | None:
    return await session.get(PanelSyncStatus, SINGLETON_ID)


async def update_panel_sync_status(
    session: AsyncSession,
    status: str,
    details: str,
    users_processed: int = 0,
    subs_synced: int = 0,
    last_sync_time: datetime | None = None,
) -> PanelSyncStatus:
    if last_sync_time is None:
        last_sync_time = datetime.now(UTC)

    sync_record = await get_panel_sync_status(session)
    if sync_record:
        sync_record.last_sync_time = last_sync_time
        sync_record.status = status
        sync_record.details = details
        sync_record.users_processed_from_panel = users_processed
        sync_record.subscriptions_synced = subs_synced
    else:
        sync_record = PanelSyncStatus(
            id=SINGLETON_ID,
            last_sync_time=last_sync_time,
            status=status,
            details=details,
            users_processed_from_panel=users_processed,
            subscriptions_synced=subs_synced,
        )
        session.add(sync_record)

    await session.flush()
    await session.refresh(sync_record)
    logging.info(
        f"Panel sync status updated: {status}, Users: {users_processed}, Subs: {subs_synced}"
    )
    return sync_record
