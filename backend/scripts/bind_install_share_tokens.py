"""Trusted one-time backfill for public tokens issued before link binding.

Run without --apply first. This queries the current panel link for each active
legacy token; no anonymous request can perform this operation.
"""

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.services.panel_api_service import PanelApiService
from config.settings import get_settings
from db.models import Subscription


async def backfill(*, apply: bool) -> tuple[int, int]:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    eligible = 0
    skipped = 0
    try:
        async with PanelApiService(settings) as panel, factory() as session:
            result = await session.scalars(
                select(Subscription).where(
                    Subscription.install_share_token.is_not(None),
                    Subscription.install_share_panel_short_uuid.is_(None),
                    Subscription.is_active.is_(True),
                    Subscription.end_date > datetime.now(UTC),
                )
            )
            for subscription in result:
                panel_user_uuid = str(subscription.panel_user_uuid or "").strip()
                if not panel_user_uuid:
                    skipped += 1
                    continue
                lookup = await panel.get_user_by_uuid_lookup(panel_user_uuid)
                panel_user = lookup.get("user") if lookup.get("ok") else None
                if not isinstance(panel_user, dict):
                    skipped += 1
                    continue
                short_uuid = str(panel_user.get("shortUuid") or "").strip()
                if not short_uuid or not panel_user.get("subscriptionUrl"):
                    skipped += 1
                    continue
                eligible += 1
                if apply:
                    await session.execute(
                        update(Subscription)
                        .where(
                            Subscription.subscription_id == subscription.subscription_id,
                            Subscription.install_share_token == subscription.install_share_token,
                            Subscription.install_share_panel_short_uuid.is_(None),
                        )
                        .values(install_share_panel_short_uuid=short_uuid)
                    )
            if apply:
                await session.commit()
    finally:
        await engine.dispose()
    return eligible, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist verified bindings")
    args = parser.parse_args()
    eligible, skipped = asyncio.run(backfill(apply=args.apply))
    print(f"verified={eligible} skipped={skipped} applied={bool(args.apply)}")


if __name__ == "__main__":
    main()
