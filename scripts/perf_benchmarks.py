from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (str(BACKEND), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from bot.services import panel_api_service  # noqa: E402
from bot.services.tariff_worker import TariffTrafficWorker  # noqa: E402
from bot.utils import config_link  # noqa: E402
from bot.utils.config_link import prepare_config_links  # noqa: E402
from bot.utils.ttl_cache import AsyncTTLCache  # noqa: E402

DEFAULT_USER_SIZES = (200, 500, 1000, 5000, 10000)


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
        settings=SimpleNamespace(TARIFF_WORKER_BULK_PANEL_FETCH_THRESHOLD=200),
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
        "estimated_bulk_http_pages_at_100": math.ceil(users / 100),
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
            "panel_user_bulk_prefetch": await bench_panel_user_prefetch(users),
            "premium_usage_1_node": await bench_premium_usage(users),
            "ttl_cache_cold_single_key": await bench_ttl_singleflight(users),
            "crypt4_same_link": await bench_crypt4(users),
        }
    return results


def _print_table(results: dict[str, dict]) -> None:
    print(
        "users | bulk_pages_est | premium_usage_s | premium_panel_calls | "
        "ttl_loader_calls | crypt4_panel_calls"
    )
    print("-" * 104)
    for users, data in results.items():
        print(
            f"{users:>5} | "
            f"{data['panel_user_bulk_prefetch']['estimated_bulk_http_pages_at_100']:>14} | "
            f"{data['premium_usage_1_node']['seconds']:>15.6f} | "
            f"{data['premium_usage_1_node']['panel_calls']:>19} | "
            f"{data['ttl_cache_cold_single_key']['loader_calls']:>16} | "
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
