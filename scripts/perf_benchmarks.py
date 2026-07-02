from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (str(BACKEND), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

import bot.app.web.subscription_webapp  # noqa: E402,F401
from bot.app.web.admin_api_impl import stats as admin_stats_module  # noqa: E402
from bot.handlers.admin.sync_admin import (  # noqa: E402
    _description_matches,
    _subscription_update_delta,
)
from bot.middlewares import profile_sync as profile_sync_module  # noqa: E402
from bot.services import panel_api_service  # noqa: E402
from bot.services.panel_api_service import PanelApiService  # noqa: E402
from bot.services.tariff_worker import TariffTrafficWorker  # noqa: E402
from bot.utils import config_link  # noqa: E402
from bot.utils.config_link import prepare_config_links  # noqa: E402
from bot.utils.ttl_cache import AsyncTTLCache  # noqa: E402

DEFAULT_USER_SIZES = (200, 500, 1000, 5000, 10000)


def estimated_panel_user_pages(users: int, page_size: int = 1000) -> int:
    if users <= 0:
        return 1
    # get_all_panel_users stops on a short/empty page, so exact page multiples
    # need one final empty-page request.
    return users // page_size + 1


class FakePanel:
    def __init__(self, users: int):
        self.calls = 0
        self.stats = {
            "topUsers": [
                {
                    "username": f"user_{index}",
                    "total": index + 1,
                }
                for index in range(users)
            ]
        }

    async def get_node_users_bandwidth_stats(self, node_uuid: str, *, start: str, end: str):
        self.calls += 1
        return self.stats


class FakeBulkPanel:
    def __init__(self, users: int):
        self.calls = 0
        self.users = [
            {"uuid": f"panel-{index}", "username": f"user_{index}"} for index in range(users)
        ]

    async def get_all_panel_users(self, page_size: int = 100, log_responses: bool = False):
        self.calls += 1
        return self.users


async def bench_premium_usage(users: int) -> dict:
    panel = FakePanel(users)
    worker = TariffTrafficWorker(
        settings=SimpleNamespace(),
        session_factory=SimpleNamespace(),
        panel_service=panel,
        subscription_service=SimpleNamespace(),
    )
    started = time.perf_counter()
    checksum = 0
    for index in range(users):
        checksum += await worker._premium_usage_for_user(
            f"uuid_{index}",
            ["node-1"],
            "2026-05-01",
            "2026-05-20",
            panel_username=f"user_{index}",
        )
    elapsed = time.perf_counter() - started
    return {
        "seconds": elapsed,
        "panel_calls": panel.calls,
        "checksum": checksum,
    }


async def bench_panel_user_prefetch(users: int) -> dict:
    panel = FakeBulkPanel(users)
    worker = TariffTrafficWorker(
        settings=SimpleNamespace(TARIFF_WORKER_BULK_PANEL_FETCH_THRESHOLD=50),
        session_factory=SimpleNamespace(),
        panel_service=panel,
        subscription_service=SimpleNamespace(),
    )
    subs = [SimpleNamespace(panel_user_uuid=f"panel-{index}") for index in range(users)]
    started = time.perf_counter()
    by_uuid = await worker._prefetch_panel_users_by_uuid(subs)
    elapsed = time.perf_counter() - started
    return {
        "seconds": elapsed,
        "service_calls": panel.calls,
        "matched": len(by_uuid or {}),
        "legacy_user_get_calls": users,
        "estimated_bulk_http_pages": estimated_panel_user_pages(users),
    }


async def bench_panel_sync_startup(users: int) -> dict:
    end_date = "2026-06-20T12:00:00+00:00"
    from datetime import datetime

    parsed_end_date = datetime.fromisoformat(end_date).astimezone(UTC)
    started = time.perf_counter()
    subscription_writes = 0
    description_patches = 0
    for index in range(users):
        desired_description = f"user{index}@example.test\nusername_{index}"
        current_description = f"user{index}@example.test username_{index}"
        if not _description_matches(current_description, desired_description):
            description_patches += 1
        subscription = SimpleNamespace(
            user_id=index,
            panel_user_uuid=f"panel-{index}",
            end_date=parsed_end_date,
            is_active=True,
            status_from_panel="ACTIVE",
        )
        delta = _subscription_update_delta(
            subscription,
            {
                "user_id": index,
                "panel_user_uuid": f"panel-{index}",
                "end_date": parsed_end_date,
                "is_active": True,
                "status_from_panel": "ACTIVE",
            },
        )
        if delta:
            subscription_writes += 1
    elapsed = time.perf_counter() - started
    return {
        "seconds": elapsed,
        "panel_get_pages_estimate": estimated_panel_user_pages(users),
        "legacy_user_lookup_queries_estimate": users * 3,
        "optimized_user_lookup_queries_estimate": 1,
        "legacy_subscription_lookup_queries_estimate": users,
        "optimized_subscription_lookup_queries_estimate": 1,
        "legacy_subscription_write_attempts": users,
        "optimized_subscription_writes": subscription_writes,
        "description_panel_patches": description_patches,
    }


async def bench_panel_user_cache(users: int) -> dict:
    settings = SimpleNamespace(
        PANEL_API_URL="https://panel.example.test/api",
        PANEL_API_KEY="key",
        USER_HWID_DEVICE_LIMIT=None,
        PANEL_USER_CACHE_TTL_SECONDS=60,
        PANEL_DEVICES_CACHE_TTL_SECONDS=60,
        PANEL_ALL_USERS_CACHE_TTL_SECONDS=60,
        PANEL_ALL_USERS_PAGE_SIZE=1000,
        REDIS_URL=None,
        REDIS_KEY_PREFIX="bench",
    )
    service = PanelApiService(settings)
    calls = 0

    async def fake_request(method, endpoint, log_full_response=False, **kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.001)
        return {"response": {"uuid": "panel-user", "username": "cached"}}

    service._request = fake_request
    started = time.perf_counter()
    await asyncio.gather(*(service.get_user_by_uuid("panel-user") for _ in range(users)))
    elapsed = time.perf_counter() - started
    return {
        "seconds": elapsed,
        "panel_calls": calls,
        "legacy_panel_calls": users,
    }


async def bench_panel_all_users_cache(users: int) -> dict:
    settings = SimpleNamespace(
        PANEL_API_URL="https://panel.example.test/api",
        PANEL_API_KEY="key",
        USER_HWID_DEVICE_LIMIT=None,
        PANEL_USER_CACHE_TTL_SECONDS=60,
        PANEL_DEVICES_CACHE_TTL_SECONDS=60,
        PANEL_ALL_USERS_CACHE_TTL_SECONDS=60,
        PANEL_ALL_USERS_PAGE_SIZE=1000,
        # Disable the inter-page courtesy delay so this measures real paging /
        # aggregation throughput rather than the fixed I/O throttle (which would
        # otherwise dominate: ~0.1s * pages).
        PANEL_ALL_USERS_PAGE_DELAY_SECONDS=0,
        REDIS_URL=None,
        REDIS_KEY_PREFIX="bench",
    )
    service = PanelApiService(settings)
    panel_users = [{"uuid": f"panel-{index}"} for index in range(users)]
    calls = 0

    async def fake_request(method, endpoint, log_full_response=False, **kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.001)
        params = kwargs.get("params") or {}
        size = int(params.get("size", 100))
        start = int(params.get("start", 0))
        return {"response": {"users": panel_users[start : start + size]}}

    service._request = fake_request
    started = time.perf_counter()
    first, second = await asyncio.gather(
        service.get_all_panel_users(),
        service.get_all_panel_users(),
    )
    elapsed = time.perf_counter() - started
    pages = estimated_panel_user_pages(users)
    return {
        "seconds": elapsed,
        "panel_calls": calls,
        "legacy_panel_calls": pages * 2,
        "users_first": len(first or []),
        "users_second": len(second or []),
    }


async def bench_panel_devices_cache(users: int) -> dict:
    settings = SimpleNamespace(
        PANEL_API_URL="https://panel.example.test/api",
        PANEL_API_KEY="key",
        USER_HWID_DEVICE_LIMIT=None,
        PANEL_USER_CACHE_TTL_SECONDS=60,
        PANEL_DEVICES_CACHE_TTL_SECONDS=60,
        PANEL_ALL_USERS_CACHE_TTL_SECONDS=60,
        PANEL_ALL_USERS_PAGE_SIZE=1000,
        REDIS_URL=None,
        REDIS_KEY_PREFIX="bench",
    )
    service = PanelApiService(settings)
    calls = 0

    async def fake_request(method, endpoint, log_full_response=False, **kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.001)
        return {"response": [{"hwid": "device-1"}]}

    service._request = fake_request
    started = time.perf_counter()
    await asyncio.gather(*(service.get_user_devices("panel-user") for _ in range(users)))
    elapsed = time.perf_counter() - started
    return {
        "seconds": elapsed,
        "panel_calls": calls,
        "legacy_panel_calls": users,
    }


async def bench_ttl_singleflight(users: int) -> dict:
    settings = SimpleNamespace(REDIS_URL="redis://example", REDIS_KEY_PREFIX="bench")
    cache = AsyncTTLCache(ttl_seconds=60, settings=settings, namespace="singleflight")
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.001)
        return {"value": 42}

    async def fake_get(settings, key):
        return None

    async def fake_set(settings, key, value, ttl):
        return None

    started = time.perf_counter()
    with (
        patch("bot.infra.redis.cache_get_json", new=fake_get),
        patch("bot.infra.redis.cache_set_json", new=fake_set),
    ):
        await asyncio.gather(*(cache.get_or_load("same-key", loader) for _ in range(users)))
    elapsed = time.perf_counter() - started
    return {
        "seconds": elapsed,
        "loader_calls": calls,
    }


class FakeAdminStatsPanel:
    def __init__(self):
        self.calls = {
            "system": 0,
            "bandwidth": 0,
            "nodes": 0,
            "nodes_bandwidth": 0,
            "online": 0,
        }

    async def get_system_stats(self):
        self.calls["system"] += 1
        await asyncio.sleep(0.001)
        return {"users": {"totalUsers": 10}}

    async def get_bandwidth_stats(self):
        self.calls["bandwidth"] += 1
        await asyncio.sleep(0.001)
        return {"current": 123}

    async def get_nodes_statistics(self):
        self.calls["nodes"] += 1
        await asyncio.sleep(0.001)
        return {"nodes": []}

    async def get_nodes_bandwidth_usage(self, *, start: str, end: str, top_nodes_limit: int = 64):
        self.calls["nodes_bandwidth"] += 1
        await asyncio.sleep(0.001)
        return {"topNodes": []}

    async def get_nodes_online_lookups(self):
        self.calls["online"] += 1
        await asyncio.sleep(0.001)
        return {"byUuid": {}, "byName": {}}


async def bench_admin_stats_cache(users: int) -> dict:
    admin_stats_module._ADMIN_PANEL_STATS_CACHES.clear()
    settings = SimpleNamespace(
        ADMIN_PANEL_STATS_CACHE_TTL_SECONDS=60,
        REDIS_URL=None,
        REDIS_KEY_PREFIX="bench",
    )
    panel = FakeAdminStatsPanel()
    started = time.perf_counter()
    await asyncio.gather(
        *(admin_stats_module._load_admin_panel_stats(None, settings, panel) for _ in range(users))
    )
    elapsed = time.perf_counter() - started
    return {
        "seconds": elapsed,
        "panel_endpoint_calls": sum(panel.calls.values()),
        "legacy_panel_endpoint_calls": users * len(panel.calls),
    }


async def bench_admin_db_stats_cache(users: int) -> dict:
    admin_stats_module._ADMIN_DB_STATS_CACHES.clear()
    settings = SimpleNamespace(
        ADMIN_DB_STATS_CACHE_TTL_SECONDS=60,
        REDIS_URL=None,
        REDIS_KEY_PREFIX="bench",
    )
    dal_calls = 0

    class FakeSessionFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return SimpleNamespace()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def fake_user_stats(session):
        nonlocal dal_calls
        dal_calls += 1
        await asyncio.sleep(0.001)
        return {
            "total_users": users,
            "banned_users": 0,
            "active_today": 0,
            "paid_subscriptions": users,
            "trial_users": 0,
            "inactive_users": 0,
            "referral_users": 0,
        }

    async def fake_financial_stats(session):
        nonlocal dal_calls
        dal_calls += 1
        await asyncio.sleep(0.001)
        return {
            "today_revenue": 0.0,
            "week_revenue": 0.0,
            "month_revenue": 0.0,
            "all_time_revenue": 0.0,
            "today_payments_count": 0,
            "daily_series": [],
        }

    async def fake_sync_status(session):
        nonlocal dal_calls
        dal_calls += 1
        await asyncio.sleep(0.001)
        return SimpleNamespace(
            status="success",
            last_sync_time=None,
            details=None,
            users_processed_from_panel=users,
            subscriptions_synced=users,
        )

    async def fake_recent_payments(session, limit=10):
        nonlocal dal_calls
        dal_calls += 1
        await asyncio.sleep(0.001)
        return []

    started = time.perf_counter()
    with (
        patch.object(admin_stats_module.user_dal, "get_enhanced_user_statistics", fake_user_stats),
        patch.object(
            admin_stats_module.payment_dal, "get_financial_statistics", fake_financial_stats
        ),
        patch.object(admin_stats_module.panel_sync_dal, "get_panel_sync_status", fake_sync_status),
        patch.object(
            admin_stats_module.payment_dal,
            "get_recent_payment_logs_with_user",
            fake_recent_payments,
        ),
    ):
        await asyncio.gather(
            *(
                admin_stats_module._load_admin_db_stats(settings, FakeSessionFactory())
                for _ in range(users)
            )
        )
    elapsed = time.perf_counter() - started
    return {
        "seconds": elapsed,
        "dal_loader_calls": dal_calls,
        "optimized_db_round_trips_per_miss_estimate": 6,
        "optimized_db_round_trips_with_cache_estimate": 6,
        "legacy_db_round_trips_estimate": users * 15,
    }


async def bench_profile_sync_guard(users: int) -> dict:
    profile_sync_module._LOCAL_PROFILE_SYNC_CHECKS.clear()
    settings = SimpleNamespace(
        PROFILE_SYNC_CACHE_TTL_SECONDS=900,
        REDIS_URL=None,
        REDIS_KEY_PREFIX="bench",
    )
    allowed_checks = 0
    started = time.perf_counter()
    for _ in range(users):
        if not await profile_sync_module._profile_sync_recently_checked(settings, 42):
            allowed_checks += 1
            await profile_sync_module._mark_profile_sync_checked(settings, 42)
    elapsed = time.perf_counter() - started
    return {
        "seconds": elapsed,
        "profile_checks_allowed": allowed_checks,
        "legacy_profile_checks": users,
    }


async def bench_crypt4(users: int) -> dict:
    config_link._CRYPT4_LINK_CACHES.clear()
    settings = SimpleNamespace(
        CRYPT4_ENABLED=True,
        CRYPT4_REDIRECT_URL="",
        CRYPT4_LINK_CACHE_TTL_SECONDS=3600,
        PANEL_API_URL="https://panel.example.test/api",
        PANEL_API_KEY="key",
        USER_HWID_DEVICE_LIMIT=None,
    )
    calls = 0

    async def fake_encrypt(self, raw_link: str):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.001)
        return "happ://crypt4/encrypted"

    async def fake_close(self):
        return None

    started = time.perf_counter()
    with (
        patch.object(panel_api_service.PanelApiService, "encrypt_happ_link", new=fake_encrypt),
        patch.object(panel_api_service.PanelApiService, "close_session", new=fake_close),
    ):
        await asyncio.gather(
            *(
                prepare_config_links(settings, "https://panel.example.test/sub/user")
                for _ in range(users)
            )
        )
    elapsed = time.perf_counter() - started
    return {
        "seconds": elapsed,
        "panel_calls": calls,
    }


async def run_suite(user_sizes: tuple[int, ...]) -> dict:
    results: dict[str, dict] = {}
    for users in user_sizes:
        results[str(users)] = {
            "panel_sync_startup": await bench_panel_sync_startup(users),
            "panel_user_bulk_prefetch": await bench_panel_user_prefetch(users),
            "panel_all_users_cache": await bench_panel_all_users_cache(users),
            "panel_user_cache": await bench_panel_user_cache(users),
            "panel_devices_cache": await bench_panel_devices_cache(users),
            "premium_usage_1_node": await bench_premium_usage(users),
            "ttl_cache_cold_single_key": await bench_ttl_singleflight(users),
            "admin_stats_cache": await bench_admin_stats_cache(users),
            "admin_db_stats_cache": await bench_admin_db_stats_cache(users),
            "profile_sync_guard": await bench_profile_sync_guard(users),
            "crypt4_same_link": await bench_crypt4(users),
        }
    return results


def _print_table(results: dict[str, dict]) -> None:
    print(
        "users | bulk_pages_est | premium_usage_s | premium_panel_calls | "
        "sync_db_reads_est | sync_db_writes | user_cache_calls | "
        "all_users_calls | device_cache_calls | admin_panel_calls | admin_db_reads_est | "
        "crypt4_panel_calls"
    )
    print("-" * 177)
    for users, data in results.items():
        sync_optimized_reads = (
            data["panel_sync_startup"]["optimized_user_lookup_queries_estimate"]
            + data["panel_sync_startup"]["optimized_subscription_lookup_queries_estimate"]
        )
        print(
            f"{users:>5} | "
            f"{data['panel_user_bulk_prefetch']['estimated_bulk_http_pages']:>14} | "
            f"{data['premium_usage_1_node']['seconds']:>15.6f} | "
            f"{data['premium_usage_1_node']['panel_calls']:>19} | "
            f"{sync_optimized_reads:>17} | "
            f"{data['panel_sync_startup']['optimized_subscription_writes']:>14} | "
            f"{data['panel_user_cache']['panel_calls']:>16} | "
            f"{data['panel_all_users_cache']['panel_calls']:>15} | "
            f"{data['panel_devices_cache']['panel_calls']:>18} | "
            f"{data['admin_stats_cache']['panel_endpoint_calls']:>17} | "
            f"{data['admin_db_stats_cache']['optimized_db_round_trips_with_cache_estimate']:>18} | "
            f"{data['crypt4_same_link']['panel_calls']:>18}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bot performance microbenchmarks.")
    parser.add_argument(
        "--users",
        default=",".join(str(value) for value in DEFAULT_USER_SIZES),
        help="Comma-separated user counts. Default: 200,500,1000,5000,10000",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON only.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    user_sizes = tuple(int(part.strip()) for part in args.users.split(",") if part.strip())
    results = asyncio.run(run_suite(user_sizes))
    if args.json:
        print(json.dumps({"results": results}, ensure_ascii=False))
        return
    _print_table(results)
    print()
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
