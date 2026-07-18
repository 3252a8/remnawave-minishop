import asyncio
from types import SimpleNamespace

from bot.payment_providers.wata import WataConfig, WataService
from bot.payment_providers.wata import rate_limit as wata_rate_limit
from bot.payment_providers.wata.rate_limit import WataGetRateLimiter, retry_after_seconds


def _service() -> WataService:
    settings = SimpleNamespace(
        DEFAULT_CURRENCY_SYMBOL="RUB",
        PAYMENT_REQUEST_TIMEOUT_SECONDS=15,
        traffic_sale_mode=False,
        trusted_proxies=[],
    )
    return WataService(
        bot=SimpleNamespace(),
        settings=settings,
        config=WataConfig(
            ENABLED=True,
            API_TOKEN="token",
            WEBHOOK_VERIFY_SIGNATURE=False,
            TRUSTED_IPS="",
        ),
        i18n=SimpleNamespace(),
        async_session_factory=SimpleNamespace(),
        subscription_service=SimpleNamespace(),
        referral_service=SimpleNamespace(),
        default_return_url="test_bot",
    )


def test_wata_search_uses_v2_and_caches_rate_limited_objects(monkeypatch):
    service = _service()
    calls = []

    async def get_json(url, *, params=None, log_prefix, profile=None):
        calls.append((url, params, log_prefix, profile.provider))
        if "/links/" in url:
            return True, {"id": "link-id", "status": "Opened"}
        return True, {"items": []}

    monkeypatch.setattr(service, "_get_json", get_json)

    async def run():
        profile = service.profile_for_method("wata")
        search = await service.search_transactions(
            order_id="465",
            statuses=("Paid", "Declined"),
            limit=10,
            profile=profile,
        )
        cached_search = await service.search_transactions(
            order_id="465",
            statuses=("Paid", "Declined"),
            limit=10,
            profile=profile,
        )
        link = await service.get_payment_link("link-id", profile=profile)
        cached_link = await service.get_payment_link("link-id", profile=profile)
        await service.close()
        return search, cached_search, link, cached_link

    search, cached_search, link, cached_link = asyncio.run(run())

    assert search == cached_search == (True, {"items": []})
    assert link == cached_link == (True, {"id": "link-id", "status": "Opened"})
    assert len(calls) == 2
    assert calls[0][0] == "https://api.wata.pro/api/h2h/v2/transactions"
    assert calls[0][1] == {
        "maxResultCount": 10,
        "orderId": "465",
        "statuses": ["Paid", "Declined"],
    }
    assert calls[1][0] == "https://api.wata.pro/api/h2h/links/link-id"


def test_wata_final_transaction_search_prefers_paid(monkeypatch):
    service = _service()
    calls = 0

    async def get_json(url, *, params=None, log_prefix, profile=None):
        nonlocal calls
        calls += 1
        return True, {
            "items": [
                {
                    "id": "tx-declined",
                    "status": "Declined",
                    "orderId": "465",
                    "paymentLinkId": "link-id",
                },
                {
                    "id": "tx-paid",
                    "status": "Paid",
                    "orderId": "465",
                    "paymentLinkId": "link-id",
                },
            ]
        }

    monkeypatch.setattr(service, "_get_json", get_json)
    payment = SimpleNamespace(
        payment_id=465,
        provider="wata",
        provider_payment_id="link-id",
    )

    async def run():
        result = await service._find_final_transaction_for_payment(payment)
        await service.close()
        return result

    result = asyncio.run(run())

    assert result is not None
    assert result["id"] == "tx-paid"
    assert calls == 1


def test_wata_rate_limiter_singleflights_concurrent_requests(monkeypatch):
    monkeypatch.setattr(wata_rate_limit.time, "monotonic", lambda: 100.0)
    limiter = WataGetRateLimiter()
    cache_key = limiter.cache_key("transaction-search", "wata", "465")
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def request():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return True, {"items": []}

    async def run():
        first = asyncio.create_task(limiter.run(cache_key, request))
        await started.wait()
        second = asyncio.create_task(limiter.run(cache_key, request))
        await asyncio.sleep(0)
        release.set()
        return await asyncio.gather(first, second)

    results = asyncio.run(run())

    assert results == [(True, {"items": []}), (True, {"items": []})]
    assert calls == 1


def test_wata_rate_limiter_honors_retry_after(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(wata_rate_limit.time, "monotonic", lambda: clock[0])
    limiter = WataGetRateLimiter()
    cache_key = limiter.cache_key("transaction-search", "wata", "465")
    calls = 0

    async def request():
        nonlocal calls
        calls += 1
        if calls == 1:
            return False, {"status": 429, "retry_after_seconds": 12}
        return True, {"items": []}

    async def run():
        first = await limiter.run(cache_key, request)
        clock[0] = 111.0
        cached = await limiter.run(cache_key, request)
        clock[0] = 112.0
        retried = await limiter.run(cache_key, request)
        return first, cached, retried

    first, cached, retried = asyncio.run(run())

    assert first == cached == (False, {"status": 429, "retry_after_seconds": 12})
    assert retried == (True, {"items": []})
    assert calls == 2


def test_wata_retry_after_parser_supports_documented_shapes():
    assert retry_after_seconds("17", None) == 17
    assert retry_after_seconds(None, {"data": {"retryAfterSeconds": 11}}) == 11
    assert retry_after_seconds(None, {"details": "Repeat after 9 seconds"}) == 9
