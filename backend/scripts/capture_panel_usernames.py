"""Capture actual legacy panel usernames before changing Remnawave generations.

Run without --apply to count verifiable links. This script reads panel users by
their already persisted native references and never changes Remnawave.
"""

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.services.panel_api_service import PanelApiService
from bot.services.panel_identity_match import (
    panel_candidate_matches_account,
    panel_origin_fingerprint,
)
from config.settings import get_settings
from db.models import User


async def capture(*, apply: bool) -> tuple[int, int, int]:
    settings = get_settings()
    current_origin = panel_origin_fingerprint(settings.PANEL_API_URL)
    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    verified = 0
    unresolved = 0
    legacy = 0
    try:
        async with PanelApiService(settings) as panel, factory() as session:
            result = await session.scalars(
                select(User).where(
                    User.panel_user_uuid.is_not(None),
                    User.panel_username.is_(None),
                )
            )
            for user in result:
                saved_reference = str(user.panel_user_uuid or "").strip()
                if not saved_reference or (
                    user.panel_origin and user.panel_origin != current_origin
                ):
                    unresolved += 1
                    continue
                lookup = await panel.get_user_by_uuid_lookup(saved_reference)
                candidate = lookup.get("user") if lookup.get("ok") else None
                actual_reference = (
                    str(candidate.get("uuid") or "").strip() if isinstance(candidate, dict) else ""
                )
                actual_username = (
                    str(candidate.get("username") or "").strip()
                    if isinstance(candidate, dict)
                    else ""
                )
                if (
                    not actual_reference
                    or actual_reference.casefold() != saved_reference.casefold()
                    or not actual_username
                    or not panel_candidate_matches_account(user, candidate)
                ):
                    unresolved += 1
                    continue
                verified += 1
                if actual_username != user.minishop_id:
                    legacy += 1
                if apply:
                    user.panel_username = actual_username
                    user.panel_username_state = (
                        "current" if actual_username == user.minishop_id else "legacy_pending"
                    )
                    user.panel_origin = current_origin
            if apply:
                await session.commit()
    finally:
        await engine.dispose()
    return verified, unresolved, legacy


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist verified usernames")
    args = parser.parse_args()
    verified, unresolved, legacy = asyncio.run(capture(apply=args.apply))
    print(f"verified={verified} unresolved={unresolved} legacy={legacy} applied={bool(args.apply)}")


if __name__ == "__main__":
    main()
