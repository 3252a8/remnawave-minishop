"""Characterization tests for provider webhook security boundaries.

These pin the *reject* paths of the service-route providers that previously had
no direct ``webhook_route`` coverage (freekassa, heleket, platega, paykilla):
disabled service (503), unauthorized source IP / auth headers (403), and invalid
signature (403). The bytes here are the live contract — any refactor that moves a
helper out of these routes (F2 step 3 / F3) must keep these responses identical.

The services are driven as unbound methods over a ``SimpleNamespace`` carrying
only the attributes each reject path touches, mirroring the existing
``test_payment_webhook_idempotency`` style. The reject branches return before any
DB access, so no session/DAL fakes are needed.
"""

import asyncio
import json
from types import SimpleNamespace

from bot.payment_providers.freekassa.service import FreeKassaService
from bot.payment_providers.heleket.service import HeleketService
from bot.payment_providers.paykilla.service import PaykillaService
from bot.payment_providers.platega.service import PlategaService


class _FakeRequest:
    def __init__(
        self, *, remote="", headers=None, body=b"", json_data=None, content_type="application/json"
    ):
        self.remote = remote
        self.headers = headers or {}
        self._body = body
        self._json = json_data
        self.content_type = content_type

    async def read(self):
        return self._body

    async def json(self):
        if self._json is not None:
            return self._json
        return json.loads(self._body.decode("utf-8"))


def _run(coro):
    return asyncio.run(coro)


# --- disabled service -> 503 --------------------------------------------------


def test_freekassa_webhook_disabled_returns_503():
    service = SimpleNamespace(configured=False)
    response = _run(FreeKassaService.webhook_route(service, _FakeRequest()))
    assert response.status == 503
    assert response.text == "freekassa_disabled"


def test_heleket_webhook_disabled_returns_503():
    service = SimpleNamespace(configured=False)
    response = _run(HeleketService.webhook_route(service, _FakeRequest()))
    assert response.status == 503
    assert response.text == "heleket_disabled"


def test_platega_webhook_disabled_returns_503():
    service = SimpleNamespace(configured=False)
    response = _run(PlategaService.webhook_route(service, _FakeRequest()))
    assert response.status == 503
    assert response.text == "platega_disabled"


def test_paykilla_webhook_disabled_returns_503():
    service = SimpleNamespace(configured=False)
    response = _run(PaykillaService.webhook_route(service, _FakeRequest()))
    assert response.status == 503
    assert response.text == "paykilla_disabled"


# --- unauthorized source IP / auth headers -> 403 ----------------------------


def test_freekassa_webhook_rejects_unauthorized_ip():
    service = SimpleNamespace(
        configured=True,
        settings=SimpleNamespace(trusted_proxies=[]),
        config=SimpleNamespace(trusted_ips_list=["1.2.3.4"]),
    )
    response = _run(FreeKassaService.webhook_route(service, _FakeRequest(remote="9.9.9.9")))
    assert response.status == 403


def test_heleket_webhook_rejects_unauthorized_ip():
    service = SimpleNamespace(
        configured=True,
        settings=SimpleNamespace(trusted_proxies=[]),
        config=SimpleNamespace(trusted_ips_list=["1.2.3.4"]),
    )
    response = _run(HeleketService.webhook_route(service, _FakeRequest(remote="9.9.9.9")))
    assert response.status == 403
    assert response.text == "forbidden"


def test_paykilla_webhook_rejects_unauthorized_ip():
    service = SimpleNamespace(
        configured=True,
        settings=SimpleNamespace(trusted_proxies=[]),
        config=SimpleNamespace(trusted_ips_list=["1.2.3.4"]),
    )
    response = _run(PaykillaService.webhook_route(service, _FakeRequest(remote="9.9.9.9")))
    assert response.status == 403
    assert response.text == "forbidden"


def test_platega_webhook_rejects_invalid_auth_headers():
    service = SimpleNamespace(configured=True, merchant_id="real-merchant", secret="real-secret")
    request = _FakeRequest(
        json_data={"id": "tx-1", "status": "CONFIRMED"},
        headers={"X-MerchantId": "wrong", "X-Secret": "wrong"},
    )
    response = _run(PlategaService.webhook_route(service, request))
    assert response.status == 403
    assert response.text == "forbidden"


# --- invalid signature -> 403 ------------------------------------------------


def test_heleket_webhook_rejects_invalid_signature():
    service = SimpleNamespace(
        configured=True,
        settings=SimpleNamespace(trusted_proxies=[]),
        config=SimpleNamespace(trusted_ips_list=[]),
        verify_webhook_signature=True,
        _verify_signature=lambda _payload: False,
    )
    request = _FakeRequest(body=json.dumps({"uuid": "u1", "status": "paid"}).encode("utf-8"))
    response = _run(HeleketService.webhook_route(service, request))
    assert response.status == 403
    assert response.text == "invalid_signature"


def test_paykilla_webhook_rejects_invalid_signature():
    service = SimpleNamespace(
        configured=True,
        settings=SimpleNamespace(trusted_proxies=[]),
        config=SimpleNamespace(trusted_ips_list=[]),
        verify_webhook_signature=True,
        _verify_webhook_signature=lambda _request, _raw: False,
    )
    request = _FakeRequest(
        body=json.dumps({"eventType": "PAYMENT_SUCCESS", "data": {}}).encode("utf-8")
    )
    response = _run(PaykillaService.webhook_route(service, request))
    assert response.status == 403
    assert response.text == "invalid_signature"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
