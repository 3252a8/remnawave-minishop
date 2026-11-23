"""Compare premium accounting paths on deterministic data, without panel or DB access."""

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import UUID

from pydantic_core import from_json

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts"), str(ROOT)]
import perf_benchmarks as bench  # noqa: E402

from config.settings import Settings  # noqa: E402

CASES = ("adapter", "v3-shared", "v3-distinct", "json-traffic", "json-users")


def panel_response(users: int) -> dict[str, Any]:
    return {
        "response": {
            "nodes": [
                {
                    "uuid": f"node-{node}",
                    "users": [{"id": uid, "totalBytes": uid} for uid in range(1, users + 1)],
                }
                for node in range(8)
            ]
        }
    }


def users_page(users: int) -> dict[str, Any]:
    return {
        "response": {
            "users": [
                {
                    "id": uid,
                    "uuid": str(UUID(int=uid)),
                    "username": f"tg_{uid}",
                    "telegramId": 10_000_000 + uid,
                    "description": f"Пользователь №{uid}",
                    "status": "ACTIVE",
                    "trafficLimitBytes": 2**40,
                    "userTraffic": {"usedTrafficBytes": uid * 181},
                    "expireAt": "2026-12-01T00:00:00Z",
                }
                for uid in range(1, users + 1)
            ]
        }
    }


async def shared_period(users: int, body: str) -> dict[str, Any]:
    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="bench",
        POSTGRES_PASSWORD="bench",
        PANEL_API_URL="https://panel.example.test/api",
        PANEL_API_KEY="x",
    )
    panel = bench.PanelApiService(settings)
    worker = bench.TariffTrafficWorker(settings, Mock(), panel, Mock())
    nodes = [f"node-{index}" for index in range(8)]
    calls = 0

    def request(method: str, url: str, **kwargs: Any) -> MagicMock:
        nonlocal calls
        if method == "GET" and url.endswith("/system/metadata"):
            text = '{"response":{"version":"3.0.0"}}'
        elif method == "POST" and url.endswith("/bandwidth-stats/nodes/usage"):
            text = body
            calls += 1
        else:
            raise AssertionError((method, url))
        response = Mock(
            status=200,
            headers={"Content-Type": "application/json"},
            content_length=len(text),
            text=AsyncMock(return_value=text),
        )
        context = MagicMock()
        context.__aenter__.return_value = response
        return context

    checksum = 0
    with patch.object(panel, "_get_session", AsyncMock(return_value=Mock(request=request))):
        started = time.perf_counter()
        for uid in range(1, users + 1):
            total = await worker._premium_usage_for_user(
                str(uid), nodes, "2026-05-01", "2026-05-20", panel_username=f"user_{uid}"
            )
            if total != 8 * uid:
                raise AssertionError((uid, total))
            checksum += total
        seconds = time.perf_counter() - started
    return {"seconds": seconds, "panel_calls": calls, "checksum": checksum}


async def measure(case: str, users: int, repeats: int) -> None:
    body = ""
    if case == "json-users":
        payload = users_page(users)
    elif case in {"v3-shared", "json-traffic"}:
        payload = panel_response(users)
    else:
        payload = {}
    if payload:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if case.startswith("json-"):
        timings: dict[str, list[float]] = {"stdlib": [], "rust_keys": []}
        for run in range(repeats):
            for name in tuple(timings) if run % 2 == 0 else tuple(reversed(timings)):
                started = time.perf_counter()
                parsed = (
                    json.loads(body)
                    if name == "stdlib"
                    else from_json(body, cache_strings="keys", allow_inf_nan=False)
                )
                timings[name].append(time.perf_counter() - started)
                if parsed != payload:
                    raise AssertionError("Decoded panel response differs")
                del parsed
        print(
            json.dumps(
                {"case": case, "users": users, "bytes": len(body.encode()), "seconds": timings}
            )
        )
        return

    samples = []
    expected_calls = users if case == "v3-distinct" else 1
    expected_checksum = users * (users + 1) // 2 * (1 if case == "adapter" else 8)
    for _ in range(repeats):
        if case == "adapter":
            result = await bench.bench_premium_usage(users)
        elif case == "v3-distinct":
            result = await bench.bench_premium_usage_8_nodes_distinct_periods(users)
        else:
            result = await shared_period(users, body)
        calls = result.get("panel_calls", result.get("optimized_panel_calls"))
        if calls != expected_calls or result["checksum"] != expected_checksum:
            raise AssertionError(result)
        samples.append(result["seconds"])
    print(
        json.dumps(
            {
                "case": case,
                "users": users,
                "median": statistics.median(samples),
                "seconds": samples,
                "usage_calls": expected_calls,
                "checksum": expected_checksum,
            }
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", nargs="+", type=int, default=[1000, 10000])
    parser.add_argument("--case", nargs="+", choices=CASES, default=CASES)
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    if min(*args.users, args.repeat) < 1:
        parser.error("User counts and repeats must be positive")
    for users in args.users:
        for case in args.case:
            asyncio.run(measure(case, users, args.repeat))


if __name__ == "__main__":
    main()
