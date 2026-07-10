from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from ..shared.http_client import HttpClientMixin, post_json_request

_MAINNET_BASE_URL = "https://pay.crypt.bot"
_TESTNET_BASE_URL = "https://testnet-pay.crypt.bot"


class CryptoPayApiError(RuntimeError):
    """Raised when Crypto Pay API returns an unusable response."""


@dataclass(frozen=True)
class CryptoPayInvoice:
    invoice_id: int
    status: str
    amount: str
    asset: str | None = None
    fiat: str | None = None
    bot_invoice_url: str = ""
    web_app_invoice_url: str | None = None
    mini_app_invoice_url: str | None = None
    payload: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> CryptoPayInvoice:
        invoice_id_value = data.get("invoice_id")
        if invoice_id_value is None:
            raise ValueError("Crypto Pay invoice response has no invoice_id")
        try:
            invoice_id = int(str(invoice_id_value))
        except ValueError as exc:
            raise ValueError("Crypto Pay invoice response has invalid invoice_id") from exc

        bot_invoice_url = _optional_str(data, "bot_invoice_url") or _optional_str(data, "pay_url")
        return cls(
            invoice_id=invoice_id,
            status=str(data.get("status") or ""),
            amount=str(data.get("amount") or "0"),
            asset=_optional_str(data, "asset") or _optional_str(data, "paid_asset"),
            fiat=_optional_str(data, "fiat"),
            bot_invoice_url=bot_invoice_url or "",
            web_app_invoice_url=_optional_str(data, "web_app_invoice_url"),
            mini_app_invoice_url=_optional_str(data, "mini_app_invoice_url"),
            payload=_optional_str(data, "payload"),
        )


@dataclass(frozen=True)
class CryptoPayUpdate:
    update_id: int
    update_type: str
    request_date: str
    payload: CryptoPayInvoice

    @classmethod
    def from_raw(cls, raw_body: bytes) -> CryptoPayUpdate:
        try:
            parsed = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Crypto Pay webhook payload is not valid JSON") from exc
        if not isinstance(parsed, Mapping):
            raise ValueError("Crypto Pay webhook payload must be an object")

        data = cast(Mapping[str, Any], parsed)
        invoice = data.get("payload")
        if not isinstance(invoice, Mapping):
            raise ValueError("Crypto Pay webhook payload has no invoice object")

        update_id = data.get("update_id")
        try:
            parsed_update_id = int(str(update_id or 0))
        except ValueError:
            parsed_update_id = 0

        return cls(
            update_id=parsed_update_id,
            update_type=str(data.get("update_type") or ""),
            request_date=str(data.get("request_date") or ""),
            payload=CryptoPayInvoice.from_mapping(cast(Mapping[str, Any], invoice)),
        )


class CryptoPayApiClient(HttpClientMixin):
    def __init__(
        self,
        *,
        token: str,
        network: str,
        total_timeout: float | Callable[[], float],
    ) -> None:
        self.token = token
        self.network = network
        self._init_http_client(total_timeout=total_timeout)

    @property
    def base_url(self) -> str:
        return _TESTNET_BASE_URL if self.network.strip().lower() == "testnet" else _MAINNET_BASE_URL

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Crypto-Pay-API-Token": self.token,
        }

    async def create_invoice(
        self,
        *,
        amount: float,
        currency_type: str,
        fiat: str | None = None,
        asset: str | None = None,
        description: str | None = None,
        payload: str | None = None,
    ) -> CryptoPayInvoice:
        body = _drop_none(
            {
                "amount": str(amount),
                "currency_type": currency_type,
                "fiat": fiat,
                "asset": asset,
                "description": description,
                "payload": payload,
            }
        )
        session = await self._get_session()
        success, response_data = await post_json_request(
            session,
            f"{self.base_url}/api/createInvoice",
            body=body,
            headers=self._headers(),
            log_prefix="CryptoPay createInvoice",
            is_success=_api_success,
        )
        if not success:
            raise CryptoPayApiError(f"Crypto Pay API rejected createInvoice: {response_data}")

        result = response_data.get("result")
        if not isinstance(result, Mapping):
            raise CryptoPayApiError("Crypto Pay createInvoice response has no result object")
        try:
            return CryptoPayInvoice.from_mapping(cast(Mapping[str, Any], result))
        except ValueError as exc:
            raise CryptoPayApiError(str(exc)) from exc


def _drop_none(data: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def _optional_str(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _api_success(status: int, body: Any) -> bool:
    return status == 200 and isinstance(body, Mapping) and body.get("ok") is True
