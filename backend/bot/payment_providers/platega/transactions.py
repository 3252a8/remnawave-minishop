import logging
from typing import TYPE_CHECKING, Any

from ..base import (
    normalize_payment_currency_code,
    parse_supported_currency_codes,
    provider_runtime_enabled,
)

logger = logging.getLogger(__name__)


class PlategaTransactionMixin:
    config: Any
    settings: Any
    _default_return_url: str

    if TYPE_CHECKING:

        async def _get_session(self) -> Any: ...

    @property
    def configured(self) -> bool:
        return bool(
            provider_runtime_enabled(
                self.config,
                "SBP_ADMIN_ONLY_ENABLED",
                "CARD_ADMIN_ONLY_ENABLED",
                "CRYPTO_ADMIN_ONLY_ENABLED",
                "INTERNATIONAL_ADMIN_ONLY_ENABLED",
                "ALL_METHODS_ADMIN_ONLY_ENABLED",
                "SUBSCRIPTION_ADMIN_ONLY_ENABLED",
            )
            and self.merchant_id
            and self.secret
        )

    @property
    def base_url(self) -> str:
        return (self.config.BASE_URL or "https://app.platega.io").rstrip("/")

    @property
    def merchant_id(self) -> str | None:
        return self.config.MERCHANT_ID

    @property
    def secret(self) -> str | None:
        return self.config.SECRET

    @property
    def payment_method(self) -> int:
        return self.config.PAYMENT_METHOD

    @property
    def sbp_method(self) -> int:
        return self.config.sbp_method_resolved

    @property
    def card_method(self) -> int:
        return self.config.CARD_METHOD

    @property
    def crypto_method(self) -> int:
        return self.config.CRYPTO_METHOD

    @property
    def international_method(self) -> int:
        return self.config.INTERNATIONAL_METHOD

    @property
    def return_url(self) -> str:
        return self.config.RETURN_URL or f"https://t.me/{self._default_return_url}"

    @property
    def failed_url(self) -> str:
        return self.config.FAILED_URL or self.return_url

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {
            "X-MerchantId": self.merchant_id or "",
            "X-Secret": self.secret or "",
            "Content-Type": "application/json",
        }

    async def create_transaction(
        self,
        *,
        amount: float,
        currency: str | None,
        description: str,
        payload: str | None = None,
        metadata: dict[str, Any] | None = None,
        payment_method: int | None = None,
        interval: int | None = None,
        allow_method_selection: bool = False,
    ) -> tuple[bool, dict[str, Any]]:
        if not self.configured:
            logger.error("PlategaService is not configured. Cannot create transaction.")
            return False, {"message": "service_not_configured"}

        currency_code = normalize_payment_currency_code(
            currency or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
        )
        supported = parse_supported_currency_codes(self.config.SUPPORTED_CURRENCIES)
        if supported and currency_code not in supported:
            return False, {
                "message": "unsupported_currency",
                "currency": currency_code,
                "supported_currencies": list(supported),
            }

        session = await self._get_session()
        endpoint = "/v2/transaction/process" if allow_method_selection else "/transaction/process"
        url = f"{self.base_url}{endpoint}"

        payment_details: dict[str, Any] = {"amount": float(amount), "currency": currency_code}
        if interval is not None:
            # Turns the same endpoint into a recurring mandate: Platega reads
            # ``interval`` only for the subscription payment method.
            payment_details["interval"] = int(interval)
        body: dict[str, Any] = {
            "paymentDetails": payment_details,
            "description": description,
            "return": self.return_url,
            "failedUrl": self.failed_url,
            "payload": payload,
            "metadata": metadata,
        }
        if not allow_method_selection:
            body["paymentMethod"] = int(
                payment_method if payment_method is not None else self.payment_method
            )

        # Remove optional keys with falsy values to avoid validation errors
        clean_body = {k: v for k, v in body.items() if v not in (None, "")}
        safe_headers = {
            "X-MerchantId": self._auth_headers.get("X-MerchantId"),
            "X-Secret": "***" if self._auth_headers.get("X-Secret") else "",
            "Content-Type": self._auth_headers.get("Content-Type"),
        }
        logger.info(
            "Platega create_transaction request: url=%s headers=%s body=%s",
            url,
            safe_headers,
            clean_body,
        )

        # Resolve through the public service module so existing integrations can
        # continue to replace the transport at that stable seam.
        from . import service as service_module

        return await service_module.post_json_request(
            session,
            url,
            body=clean_body,
            headers=self._auth_headers,
            log_prefix="Platega create_transaction",
        )
