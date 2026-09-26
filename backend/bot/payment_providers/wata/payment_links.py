import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from ..base import normalize_payment_currency_code
from ..shared import first_value, format_decimal_amount
from .config import (
    WATA_CRYPTO_PROVIDER,
    WATA_PROVIDER,
    WataTerminalProfile,
    _normalize_terminal_public_id,
    _wata_provider_from_method,
    _wata_success_status,
)

logger = logging.getLogger(__name__)


class WataPaymentLinkMixin:
    config: Any
    settings: Any
    _cached_public_key_pem: dict[str, str | None]
    _default_return_url: str
    _get_rate_limiter: Any

    if TYPE_CHECKING:

        async def _get_session(self) -> Any: ...

    @property
    def base_url(self) -> str:
        return (self.config.BASE_URL or "https://api.wata.pro/api/h2h").rstrip("/")

    def profile_for_method(self, method: Any = WATA_PROVIDER) -> WataTerminalProfile:
        return self.config.profile_for_method(method)

    def profile_for_payment(self, payment: Any) -> WataTerminalProfile:
        return self.profile_for_method(getattr(payment, "provider", None))

    def profile_enabled(self, method: Any = WATA_PROVIDER) -> bool:
        provider = _wata_provider_from_method(method)
        if provider == WATA_CRYPTO_PROVIDER:
            return self.config.crypto_runtime_enabled
        return self.config.fiat_runtime_enabled

    def iter_enabled_profiles(self) -> tuple[WataTerminalProfile, ...]:
        profiles: list[WataTerminalProfile] = []
        for provider in (WATA_PROVIDER, WATA_CRYPTO_PROVIDER):
            profile = self.profile_for_method(provider)
            if self.profile_enabled(provider):
                profiles.append(profile)
        return tuple(profiles)

    def profile_for_terminal_public_id(
        self,
        terminal_public_id: Any,
    ) -> WataTerminalProfile | None:
        normalized = _normalize_terminal_public_id(terminal_public_id)
        if not normalized:
            return None
        for profile in self.iter_enabled_profiles():
            if _normalize_terminal_public_id(profile.terminal_public_id) == normalized:
                return profile
        return None

    @property
    def api_token(self) -> str:
        return self.profile_for_method(WATA_PROVIDER).api_token

    @property
    def return_url(self) -> str:
        return self._return_url_for_profile(self.profile_for_method(WATA_PROVIDER))

    @property
    def failed_url(self) -> str:
        return self._failed_url_for_profile(self.profile_for_method(WATA_PROVIDER))

    @property
    def payment_link_ttl_minutes(self) -> int:
        return self.profile_for_method(WATA_PROVIDER).link_ttl_minutes

    @property
    def verify_webhook_signature(self) -> bool:
        return self.config.WEBHOOK_VERIFY_SIGNATURE

    @property
    def _public_key_pem(self) -> str | None:
        profile = self.profile_for_method(WATA_PROVIDER)
        return profile.public_key or self._cached_public_key_pem.get(profile.provider)

    @_public_key_pem.setter
    def _public_key_pem(self, value: str) -> None:
        self._cached_public_key_pem[WATA_PROVIDER] = value

    def _return_url_for_profile(self, profile: WataTerminalProfile) -> str:
        return profile.return_url or f"https://t.me/{self._default_return_url}"

    def _failed_url_for_profile(self, profile: WataTerminalProfile) -> str:
        return profile.failed_url or self._return_url_for_profile(profile)

    def _auth_headers(
        self,
        profile: WataTerminalProfile | None = None,
    ) -> dict[str, str]:
        resolved = profile or self.profile_for_method(WATA_PROVIDER)
        return {
            "Authorization": f"Bearer {resolved.api_token}",
            "Content-Type": "application/json",
        }

    async def create_payment_link(
        self,
        *,
        payment_db_id: int,
        amount: float,
        currency: str | None,
        description: str,
        method: Any = WATA_PROVIDER,
        payer_email: str | None = None,
        payer_phone: str | None = None,
        subscription: Mapping[str, Any] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        profile = self.profile_for_method(method)
        if not self.profile_enabled(profile.provider):
            logger.error(
                "%s service profile is not configured. Cannot create payment link.",
                profile.log_label,
            )
            return False, {"message": "service_not_configured"}

        currency_code = normalize_payment_currency_code(
            currency or self.settings.DEFAULT_CURRENCY_SYMBOL or "RUB"
        )
        if currency_code not in profile.supported_currencies:
            return False, {
                "message": "unsupported_currency",
                "currency": currency_code,
                "supported_currencies": list(profile.supported_currencies),
            }

        session = await self._get_session()
        expires_at = (datetime.now(UTC) + timedelta(minutes=profile.link_ttl_minutes)).replace(
            microsecond=0
        )
        body: dict[str, Any] = {
            "amount": float(format_decimal_amount(amount)),
            "currency": currency_code,
            "description": description,
            "orderId": str(payment_db_id),
            "successRedirectUrl": self._return_url_for_profile(profile),
            "failRedirectUrl": self._failed_url_for_profile(profile),
            "expirationDateTime": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if subscription is not None:
            body.update(
                {
                    "type": "OneTime",
                    "email": str(payer_email or "").strip(),
                    "phone": str(payer_phone or "").strip(),
                    "subscription": dict(subscription),
                }
            )
        # Resolve through the public service module so existing integrations can
        # continue to replace the transport at that stable seam.
        from . import service as service_module

        result = await service_module.post_json_request(
            session,
            f"{self.base_url}/links",
            body=body,
            headers=self._auth_headers(profile),
            log_prefix=f"{profile.log_label} create_payment_link",
            is_success=_wata_success_status,
        )
        success, data = result
        payment_link_id = first_value(data, "id", "paymentLinkId") if success else None
        if payment_link_id:
            self._get_rate_limiter.remember(
                self._get_rate_limiter.cache_key("link", profile.provider, str(payment_link_id)),
                result,
            )
        return result
