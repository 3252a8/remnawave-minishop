"""Compatibility at the HTTP boundary for clients predating day periods."""

from typing import Any

from aiohttp import web


def day_periods_supported(request: web.Request) -> bool:
    return request.headers.get("X-Billing-Period-Unit") == "day"


def periods_for_client(request: web.Request, plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if day_periods_supported(request):
        return plans
    return [plan for plan in plans if not plan.get("duration_days") or plan.get("months")]


def targets_for_client(request: web.Request, targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if day_periods_supported(request):
        return targets
    return [
        {**target, "actions": periods_for_client(request, target.get("actions", []))}
        for target in targets
    ]
