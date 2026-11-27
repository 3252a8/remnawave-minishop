import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.plugins.builtin.blacklist.migrations import migrations
from bot.plugins.builtin.blacklist.settings import DEFAULT_SETTINGS
from bot.plugins.builtin.blacklist.sources import Reason, parse_source
from bot.plugins.builtin.blacklist.storage import (
    Match,
    claim_due_sources,
    get_matches,
    get_settings,
    list_source_statuses,
    record_refresh,
    request_source_refresh,
    save_settings,
    source_refresh_pending,
)
from db.extension_models import ExtensionOperation
from db.migrator.engine import run_migration_chains
from db.models import User


def test_source_leases_and_snapshots() -> None:
    asyncio.run(_source_leases_and_snapshots())


async def _source_leases_and_snapshots() -> None:
    database = os.environ.get("CORE_PERFORMANCE_TEST_DATABASE_URL", "")
    if not database:
        pytest.skip("CORE_PERFORMANCE_TEST_DATABASE_URL is not set")

    schema = f"blacklist_test_{uuid4().hex}"
    admin = create_async_engine(database)
    engine = create_async_engine(
        database, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {schema}"))
        chain = migrations()
        now = datetime(2026, 1, 1, tzinfo=UTC)
        operations = ExtensionOperation.__table__
        retiring = {f"test-{state}": state for state in ("queued", "blocked", "running")}
        retained = {"sent-test": "succeeded", "customer-alert": "queued", "other-plugin": "queued"}
        async with engine.begin() as connection:
            await connection.run_sync(User.__table__.create)
            await connection.run_sync(operations.create)
            await connection.run_sync(run_migration_chains, {"minishop-blacklist": chain[:1]})
            await connection.execute(
                text("UPDATE ext_minishop_blacklist_settings SET refresh_hours = 36")
            )
        async with engine.begin() as connection:
            await connection.run_sync(run_migration_chains, {"minishop-blacklist": chain[:3]})
            await connection.execute(
                text(
                    "INSERT INTO ext_minishop_blacklist_diagnostics (event, status) "
                    "VALUES ('test', 'sent')"
                )
            )
            jobs = retiring | retained
            await connection.execute(
                operations.insert(),
                [
                    {
                        "id": key,
                        "owner": "example" if key == "other-plugin" else "minishop-blacklist",
                        "kind": "send-alert" if key == "customer-alert" else "test-alert",
                        "idempotency_key": key,
                        "payload_json": "{}",
                        "state": value,
                        "lease_token": "held-lease" if value == "running" else None,
                        "lease_until": now + timedelta(minutes=1) if value == "running" else None,
                        "not_before": now,
                        "created_at": now,
                        "updated_at": now,
                    }
                    for key, value in jobs.items()
                ],
            )
        async with engine.begin() as connection:
            await connection.run_sync(run_migration_chains, {"minishop-blacklist": chain[:-1]})
            rows = (await connection.execute(select(operations))).mappings().all()
            assert {row["id"]: row["state"] for row in rows} == dict.fromkeys(
                retiring, "failed"
            ) | retained
            for row in rows:
                if row["id"] in retiring:
                    assert row["error_code"] == "blacklist_test_alert_removed"
                    assert row["lease_token"] is None and row["lease_until"] is None
            assert (
                await connection.scalar(
                    text("SELECT count(*) FROM ext_minishop_blacklist_diagnostics")
                )
                == 1
            )

        async with engine.begin() as connection:
            await connection.run_sync(run_migration_chains, {"minishop-blacklist": chain})

        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions.begin() as session:
            assert await get_settings(session) == replace(DEFAULT_SETTINGS, refresh_hours=36)
            await save_settings(session, DEFAULT_SETTINGS)
            session.add(User(user_id=7, telegram_id=1001, is_banned=False))
            assert await get_matches(session, [1001]) == {1001: Match("unknown")}
            first, second = await claim_due_sources(session, now)
            async with sessions.begin() as competing:
                assert await claim_due_sources(competing, now) == []

        async with sessions.begin() as session:
            assert await claim_due_sources(session, now) == []
            assert await record_refresh(
                session,
                first,
                now,
                snapshot=parse_source(b"1001 # first\n1002 # other\n500 # no user"),
            )
            assert await record_refresh(
                session, second, now, snapshot=parse_source(b"1001 # first\n1001 # second")
            )
            assert await get_matches(session, [1001, 1003]) == {
                1001: Match("match", (Reason("first"), Reason("second"))),
                1003: Match("clear"),
            }
            assert (await session.execute(select(User.user_id, User.is_banned))).all() == [
                (7, False)
            ]
            versions = text(
                "SELECT source_id, xmin::text FROM ext_minishop_blacklist_entries "
                "WHERE telegram_id = 1001 ORDER BY source_id"
            )
            original_versions = (await session.execute(versions)).all()

        async with sessions.begin() as session:
            now += timedelta(days=1)
            again, edited = await claim_due_sources(session, now)
            assert again.content_sha256 and edited.content_sha256
            assert await record_refresh(session, again, now)
            assert await record_refresh(
                session, edited, now, snapshot=parse_source(b"1001 # first\n1001 # second\n99")
            )
            assert (await session.execute(versions)).all() == original_versions

        async with sessions.begin() as session:
            # A 1.0.0 worker can publish new rows without knowing about the digest.
            await session.execute(
                text(
                    "DELETE FROM ext_minishop_blacklist_entries "
                    "WHERE source_id = :id AND telegram_id = 1002"
                ),
                {"id": first.source_id},
            )
            await session.execute(
                text(
                    "UPDATE ext_minishop_blacklist_sources "
                    "SET last_success_at = :time WHERE id = :id"
                ),
                {"id": first.source_id, "time": now + timedelta(minutes=1)},
            )
            now += timedelta(days=1)
            restored, unchanged = await claim_due_sources(session, now)
            assert restored.content_sha256 is None and unchanged.content_sha256
            assert await record_refresh(
                session,
                restored,
                now,
                snapshot=parse_source(b"1001 # first\n1002 # other\n500 # no user"),
            )
            assert await record_refresh(session, unchanged, now)
            assert (await get_matches(session, [1002]))[1002].state == "match"

        async with sessions.begin() as session:
            one_hour_later = now + timedelta(hours=1)
            assert await claim_due_sources(session, one_hour_later) == []
            await save_settings(session, replace(DEFAULT_SETTINGS, refresh_hours=1))
            next_first, next_second = await claim_due_sources(session, one_hour_later)
            assert not await record_refresh(session, first, one_hour_later, error="source_timeout")
            assert await record_refresh(session, next_first, one_hour_later, error="source_timeout")
            assert await record_refresh(
                session, next_second, one_hour_later, snapshot=parse_source(b"")
            )
            statuses = await list_source_statuses(session)
            assert statuses[0].count == 3
            assert statuses[0].last_success_at == now
            assert statuses[0].last_attempt_at == one_hour_later
            assert statuses[0].last_error == "source_timeout"
            assert statuses[1].count == 0
            assert await get_matches(session, [1001, 1002, 1003]) == {
                1001: Match("match", (Reason("first"),), stale=True),
                1002: Match("match", (Reason("other"),), stale=True),
                1003: Match("unknown"),
            }

        async with sessions.begin() as session:
            await save_settings(session, replace(DEFAULT_SETTINGS, sources=(second.url,)))
            assert await get_matches(session, [1001]) == {1001: Match("clear")}
            await save_settings(session, replace(DEFAULT_SETTINGS, sources=()))
            assert await get_matches(session, [1001]) == {1001: Match("unknown")}
            await save_settings(session, DEFAULT_SETTINGS)
            new_first, new_second = await claim_due_sources(session, now)
            assert (first.url, second.url) == (new_first.url, new_second.url)
            assert (first.source_id, second.source_id) != (
                new_first.source_id,
                new_second.source_id,
            )

            completed_at = datetime.now(UTC)
            for lease in (new_first, new_second):
                assert await record_refresh(
                    session, lease, completed_at, snapshot=parse_source(b"1001 # previous")
                )

        async with sessions.begin() as session:
            assert not await source_refresh_pending(session)
            assert await claim_due_sources(session, datetime.now(UTC)) == []
            await request_source_refresh(session)
            assert await source_refresh_pending(session)

        async with sessions.begin() as session:
            manual_first, manual_second = await claim_due_sources(session, datetime.now(UTC))

        async with sessions.begin() as session:
            assert await source_refresh_pending(session)
            await request_source_refresh(session)
            assert await claim_due_sources(session, datetime.now(UTC)) == []
            assert await record_refresh(
                session, manual_first, datetime.now(UTC), snapshot=parse_source(b"1002 # updated")
            )
            assert await source_refresh_pending(session)
            assert await record_refresh(
                session, manual_second, datetime.now(UTC), error="source_timeout"
            )
            assert not await source_refresh_pending(session)
            assert await claim_due_sources(session, datetime.now(UTC)) == []
            assert await get_matches(session, [1001, 1002]) == {
                1001: Match("match", (Reason("previous"),), stale=True),
                1002: Match("match", (Reason("updated"),)),
            }

        async with sessions.begin() as session:
            await request_source_refresh(session)
            assert await source_refresh_pending(session)
            await save_settings(session, replace(DEFAULT_SETTINGS, sources=()))
            assert not await source_refresh_pending(session)
            assert await claim_due_sources(session, datetime.now(UTC)) == []
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await admin.dispose()
