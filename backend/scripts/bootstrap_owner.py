"""Grant the initial owner from a trusted local shell after email verification."""

import argparse
import asyncio

from bot.services.account_roles import bootstrap_owner
from config.settings import get_settings
from db.database_setup import init_db, init_db_connection


async def main(email: str) -> None:
    settings = get_settings()
    session_factory = init_db_connection(settings)
    await init_db(settings, session_factory)
    async with session_factory() as session:
        user_id = await bootstrap_owner(session, email)
        await session.commit()
    print(f"Owner role assigned to account {user_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap the first owner by verified email")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    asyncio.run(main(args.email))
