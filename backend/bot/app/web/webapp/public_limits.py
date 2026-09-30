"""HTML, raw and JSON subscription representations share the same quotas."""

import hashlib

from aiohttp import web

from .rate_limits import check_request_limits, client_ip


async def public_subscription_limit(request: web.Request, token: str) -> web.Response | None:
    digest = hashlib.sha256(token.encode()).hexdigest()
    return await check_request_limits(
        request,
        (
            (f"public-subscription:ip:{client_ip(request)}", 240),
            (f"public-subscription:token:{digest}", 60),
        ),
        window_seconds=60,
    )
