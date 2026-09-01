from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.payment_providers.cryptopay import client as client_module
from bot.payment_providers.cryptopay.client import CryptoPayApiClient, CryptoPayApiError
from bot.payment_providers.cryptopay.service import (
    CryptoPayConfig,
    CryptoPayService,
)


def test_get_invoices_exposes_unauthorized_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CryptoPayApiClient(token="secret", network="mainnet", total_timeout=1)
    monkeypatch.setattr(client, "_get_session", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        client_module,
        "post_json_request",
        AsyncMock(
            return_value=(
                False,
                {
                    "status": 401,
                    "message": {
                        "ok": False,
                        "error": {"code": 401, "name": "UNAUTHORIZED"},
                    },
                },
            )
        ),
    )

    with pytest.raises(CryptoPayApiError) as exc_info:
        asyncio.run(client.get_invoices(invoice_ids="33326234"))

    assert exc_info.value.is_unauthorized
    assert exc_info.value.status_code == 401
    assert exc_info.value.error_code == 401


def test_unauthorized_invoice_lookup_suspends_reconciliation_until_config_changes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = CryptoPayService.__new__(CryptoPayService)
    service.config = CryptoPayConfig(TOKEN="secret", NETWORK="mainnet")
    service.settings = SimpleNamespace(PAYMENT_REQUEST_TIMEOUT_SECONDS=20.0)
    service._client = SimpleNamespace(
        get_invoices=AsyncMock(
            side_effect=CryptoPayApiError(
                "unauthorized",
                status_code=401,
                error_code=401,
                error_name="UNAUTHORIZED",
            )
        )
    )
    service._client_token = "secret"
    service._client_network = "mainnet"
    service._invoice_lookup_authorization_blocked = False

    async def lookup_twice() -> tuple[object | None, object | None]:
        return await service.get_invoice("33326234"), await service.get_invoice("33326234")

    with caplog.at_level(logging.ERROR):
        first, second = asyncio.run(lookup_twice())

    assert first is None
    assert second is None
    service._client.get_invoices.assert_awaited_once_with(invoice_ids="33326234")
    assert caplog.messages == [
        "CryptoPay invoice reconciliation suspended: the API rejected the configured "
        "credentials for network=mainnet. Update CRYPTOPAY_TOKEN or CRYPTOPAY_NETWORK "
        "to resume polling."
    ]
