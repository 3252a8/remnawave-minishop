"""Grant the initial owner from a trusted local shell after email verification."""

import argparse
import asyncio

from bot.services.account_roles import bootstrap_owner
from config.settings import get_settings
from db.database_setup import init_db, init_db_connection


async def main(email: str | None, minishop_id: str | None) -> None:
    settings = get_settings()
    session_factory = init_db_connection(settings)
    await init_db(settings, session_factory)
    async with session_factory() as session:
        user_id = await bootstrap_owner(session, email=email, minishop_id=minishop_id)
        await session.commit()
    print(f"Owner role assigned to account {user_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Bootstrap the first owner from an existing account"
    )
    identifier = parser.add_mutually_exclusive_group(required=True)
    identifier.add_argument("--email", help="Verified account email")
    identifier.add_argument("--minishop-id", help="Existing account ID shown in the profile")
    args = parser.parse_args()
    asyncio.run(main(args.email, args.minishop_id))
