import base64
import json
import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from aiogram import Bot
from aiohttp import web
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from db.dal import payment_dal

from ..base import (
    normalize_payment_currency_code,
)
from ..shared import (
    HttpClientMixin,
    PaymentSuccessRequest,
    check_webhook_source_ip,
    finalize_successful_payment,
    first_value,
    format_decimal_amount,
    lookup_payment_by_order_or_provider_id,
    notify_user_payment_failed,
    payment_amount_and_currency_match,
    payment_units_for_activation,
    post_json_request,
)
from .config import (
    _WATA_IN_PROGRESS_STATUSES,
    _WATA_LINK_OPENED_STATUSES,
    WATA_CRYPTO_PROVIDER,
    WATA_PROVIDER,
    WataConfig,
    WataTerminalProfile,
    _normalize_terminal_public_id,
    _normalized_wata_status,
    _parse_wata_datetime,
    _wata_payment_link_id,
    _wata_provider_from_method,
    _wata_success_status,
    _wata_transaction_id,
)
from .rate_limit import WataGetRateLimiter, retry_after_seconds

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    ReferralService = object
    SubscriptionService = object

logger = logging.getLogger(__name__)


class WataService(HttpClientMixin):
    def __init__(
        self,
        *,
        bot: Bot,
        settings: Settings,
        config: WataConfig,
        i18n: JsonI18n,
        async_session_factory: sessionmaker,
        subscription_service: SubscriptionService,
        referral_service: ReferralService,
        default_return_url: str,
    ):
        self.bot = bot
        self.settings = settings
        self.config = config
        self.i18n = i18n
        self.async_session_factory = async_session_factory
        self.subscription_service = subscription_service
        self.referral_service = referral_service
        self._default_return_url = default_return_url
        self._cached_public_key_pem: dict[str, str | None] = {}
        self._get_rate_limiter = WataGetRateLimiter()

        self._init_http_client(total_timeout=lambda: self.settings.PAYMENT_REQUEST_TIMEOUT_SECONDS)
        if not self.configured:
            logger.warning("WataService initialized but not fully configured. Payments disabled.")

    @property
    def configured(self) -> bool:
        return bool(self.config.fiat_runtime_enabled or self.config.crypto_runtime_enabled)

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
        result = await post_json_request(
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

    async def _rate_limited_get_json(
        self,
        resource: str,
        object_id: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        log_prefix: str,
        profile: WataTerminalProfile,
    ) -> tuple[bool, dict[str, Any]]:
        cache_key = self._get_rate_limiter.cache_key(resource, profile.provider, object_id)
        return await self._get_rate_limiter.run(
            cache_key,
            lambda: self._get_json(
                url,
                params=params,
                log_prefix=log_prefix,
                profile=profile,
            ),
        )

    async def _get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        log_prefix: str,
        profile: WataTerminalProfile | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        resolved_profile = profile or self.profile_for_method(WATA_PROVIDER)
        if not self.profile_enabled(resolved_profile.provider):
            logger.error(
                "%s service profile is not configured. Cannot fetch provider state.",
                resolved_profile.log_label,
            )
            return False, {"message": "service_not_configured"}

        session = await self._get_session()
        try:
            async with session.get(
                url,
                params=dict(params or {}),
                headers=self._auth_headers(resolved_profile),
            ) as response:
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError:
                    logger.error("%s: invalid JSON response: %s", log_prefix, response_text)
                    return False, {
                        "status": response.status,
                        "message": "invalid_json",
                        "raw": response_text,
                    }
                if not _wata_success_status(response.status, response_data):
                    logger.error(
                        "%s: API returned error (status=%s, body=%s)",
                        log_prefix,
                        response.status,
                        response_data,
                    )
                    error_data: dict[str, Any] = {
                        "status": response.status,
                        "message": response_data,
                    }
                    if response.status == 429:
                        retry_after = retry_after_seconds(
                            response.headers.get("Retry-After"),
                            response_data if isinstance(response_data, Mapping) else None,
                        )
                        if retry_after is not None:
                            error_data["retry_after_seconds"] = retry_after
                    return False, error_data
                return True, response_data
        except Exception as exc:
            logger.exception("%s: request failed.", log_prefix)
            return False, {"message": str(exc)}

    async def get_payment_link(
        self,
        payment_link_id: str,
        *,
        profile: WataTerminalProfile | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        resolved_profile = profile or self.profile_for_method(WATA_PROVIDER)
        return await self._rate_limited_get_json(
            "link",
            payment_link_id,
            f"{self.base_url}/links/{payment_link_id}",
            log_prefix="Wata get_payment_link",
            profile=resolved_profile,
        )

    async def try_reuse_pending_link(self, payment: Any) -> str | None:
        """Return the existing payment link URL if it's still usable; else None.

        Used to avoid creating duplicate Wata links each time a user re-clicks
        the pay button. Repeated abandoned links inflate Wata's anti-fraud
        signals and can cause downstream bank-side rejections during the
        bank-selection step.
        """
        profile = self.profile_for_payment(payment)
        if not self.profile_enabled(profile.provider):
            return None
        provider_payment_id = str(getattr(payment, "provider_payment_id", "") or "").strip()
        if not provider_payment_id:
            return None

        success, data = await self.get_payment_link(provider_payment_id, profile=profile)
        if not success or not isinstance(data, dict):
            return None

        returned_ids = {
            str(data.get("id") or "").strip(),
            str(data.get("paymentLinkId") or "").strip(),
            str(data.get("payment_link_id") or "").strip(),
        }
        returned_ids.discard("")
        if returned_ids and provider_payment_id not in returned_ids:
            return None

        order_id = first_value(data, "orderId", "order_id")
        if order_id is not None and str(order_id) != str(payment.payment_id):
            return None

        status = _normalized_wata_status(data) or str(data.get("status") or "").strip().lower()
        if status and status not in _WATA_LINK_OPENED_STATUSES:
            return None

        expiration_raw = data.get("expirationDateTime") or data.get("expiration_date_time")
        if expiration_raw:
            exp_dt = _parse_wata_datetime(expiration_raw)
            if exp_dt is None:
                logger.warning(
                    "Wata try_reuse_pending_link: unparseable expirationDateTime %r",
                    expiration_raw,
                )
                return None
            if exp_dt <= datetime.now(UTC):
                return None

        return first_value(data, "url", "paymentUrl", "payment_url")

    async def get_transaction(
        self,
        transaction_id: str,
        *,
        profile: WataTerminalProfile | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        resolved_profile = profile or self.profile_for_method(WATA_PROVIDER)
        return await self._rate_limited_get_json(
            "transaction",
            transaction_id,
            f"{self.base_url}/transactions/{transaction_id}",
            log_prefix="Wata get_transaction",
            profile=resolved_profile,
        )

    async def search_transactions(
        self,
        *,
        order_id: str | None = None,
        payment_link_id: str | None = None,
        status: str | None = None,
        statuses: Sequence[str] | None = None,
        limit: int = 5,
        profile: WataTerminalProfile | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        params: dict[str, Any] = {
            "maxResultCount": max(1, min(int(limit or 5), 1000)),
        }
        if order_id:
            params["orderId"] = order_id
        if payment_link_id:
            params["paymentLinkIds"] = [payment_link_id]
        requested_statuses = tuple(statuses or ())
        if status and status not in requested_statuses:
            requested_statuses = (*requested_statuses, status)
        if requested_statuses:
            params["statuses"] = list(requested_statuses)

        resolved_profile = profile or self.profile_for_method(WATA_PROVIDER)
        object_id = order_id or "*"
        return await self._rate_limited_get_json(
            "transaction-search",
            object_id,
            f"{self.base_url}/v2/transactions",
            params=params,
            log_prefix="Wata search_transactions",
            profile=resolved_profile,
        )

    async def _get_public_key_pem(
        self,
        profile: WataTerminalProfile | None = None,
    ) -> str | None:
        resolved_profile = profile or self.profile_for_method(WATA_PROVIDER)
        if resolved_profile.public_key:
            value = resolved_profile.public_key
            return value.replace("\\n", "\n") if isinstance(value, str) else None

        cached = self._cached_public_key_pem.get(resolved_profile.provider)
        if cached:
            value = cached
            return value.replace("\\n", "\n") if isinstance(value, str) else None

        session = await self._get_session()
        try:
            async with session.get(
                f"{self.base_url}/public-key",
                headers=self._auth_headers(resolved_profile),
            ) as response:
                if response.status != 200:
                    logger.error("Wata public key request failed with status %s", response.status)
                    return None
                data = await response.json()
                fetched_value: Any = data.get("value") if isinstance(data, dict) else None
                if isinstance(fetched_value, str) and fetched_value.strip():
                    self._cached_public_key_pem[resolved_profile.provider] = fetched_value
                    return fetched_value.replace("\\n", "\n")
        except Exception:
            logger.exception("Wata public key request failed.")
        return None

    async def _verify_signature_with_profile(
        self,
        raw_body: bytes,
        signature_header: str,
        profile: WataTerminalProfile,
    ) -> bool:
        if not signature_header:
            return False
        public_key_pem = await self._get_public_key_pem(profile)
        if not public_key_pem:
            return False
        try:
            public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
            if not isinstance(public_key, rsa.RSAPublicKey):
                logger.warning("Wata webhook: public key is not an RSA key.")
                return False
            signature = base64.b64decode(signature_header)
            public_key.verify(signature, raw_body, padding.PKCS1v15(), hashes.SHA512())
            return True
        except (InvalidSignature, ValueError, TypeError):
            logger.warning("Wata webhook: invalid signature.")
            return False
        except Exception:
            logger.exception("Wata webhook: signature verification failed.")
            return False

    async def _verify_signature(
        self,
        raw_body: bytes,
        signature_header: str,
        *,
        profile: WataTerminalProfile | None = None,
    ) -> bool:
        if not signature_header:
            return False
        profiles = (profile,) if profile else self.iter_enabled_profiles()
        if not profiles:
            profiles = (self.profile_for_method(WATA_PROVIDER),)

        checked_keys: set[tuple[str, str]] = set()
        for candidate in profiles:
            cache_key = (
                candidate.provider,
                str(
                    candidate.public_key
                    or self._cached_public_key_pem.get(candidate.provider)
                    or ""
                ),
            )
            if cache_key in checked_keys:
                continue
            checked_keys.add(cache_key)
            if await self._verify_signature_with_profile(raw_body, signature_header, candidate):
                return True
        return False

    def _profile_hint_from_raw_body(self, raw_body: bytes) -> WataTerminalProfile | None:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            return None
        if not isinstance(payload, Mapping):
            return None
        return self.profile_for_terminal_public_id(payload.get("terminalPublicId"))

    def _payload_matches_profile(
        self,
        payload: Mapping[str, Any],
        profile: WataTerminalProfile,
    ) -> bool:
        terminal_public_id = _normalize_terminal_public_id(payload.get("terminalPublicId"))
        expected_public_id = _normalize_terminal_public_id(profile.terminal_public_id)
        if expected_public_id and terminal_public_id and terminal_public_id != expected_public_id:
            logger.warning(
                "Wata webhook terminal mismatch: provider=%s expected_public_id=%s got=%s",
                profile.provider,
                profile.terminal_public_id,
                payload.get("terminalPublicId"),
            )
            return False
        return True

    def _transaction_matches_payment(
        self,
        payload: Mapping[str, Any],
        payment: Any,
        *,
        provider_payment_id: str | None,
    ) -> bool:
        order_id = str(payload.get("orderId") or "").strip()
        if order_id and order_id == str(payment.payment_id):
            return True

        payment_link_id = _wata_payment_link_id(payload)
        if payment_link_id and provider_payment_id and payment_link_id == provider_payment_id:
            return True

        transaction_id = _wata_transaction_id(payload)
        return bool(
            transaction_id and provider_payment_id and transaction_id == provider_payment_id
        )

    async def _find_final_transaction_for_payment(
        self,
        payment: Any,
    ) -> dict[str, Any] | None:
        profile = self.profile_for_payment(payment)
        if not self.profile_enabled(profile.provider):
            return None
        provider_payment_id = str(getattr(payment, "provider_payment_id", "") or "").strip()
        success, response_data = await self.search_transactions(
            order_id=str(payment.payment_id),
            statuses=("Paid", "Declined"),
            limit=10,
            profile=profile,
        )
        if not success:
            return None

        items = response_data.get("items") or []
        for target_status in ("paid", "declined"):
            for item in items:
                if not isinstance(item, dict):
                    continue
                if _normalized_wata_status(item) != target_status:
                    continue
                if self._transaction_matches_payment(
                    item,
                    payment,
                    provider_payment_id=provider_payment_id or None,
                ) and self._payload_matches_profile(item, profile):
                    return item
        return None

    async def _mark_paid_from_payload(
        self,
        session: AsyncSession,
        payment: Any,
        payload: Mapping[str, Any],
        *,
        log_prefix: str,
    ) -> Any | None:
        current = await payment_dal.get_payment_by_db_id(session, payment.payment_id)
        if current:
            payment = current
        if payment.status == "succeeded":
            return payment

        transaction_id = _wata_transaction_id(payload) or str(payment.payment_id)

        if not self._paid_payload_matches_payment(
            payment,
            payload,
            log_prefix=log_prefix,
        ):
            return None

        try:
            claimed_payment = await payment_dal.claim_payment_finalization(
                session,
                payment.payment_id,
                provider_payment_id=transaction_id,
            )
        except Exception:
            await session.rollback()
            logger.exception(
                "%s: failed to mark payment %s as succeeded.",
                log_prefix,
                transaction_id,
            )
            return None

        if claimed_payment is None:
            return (
                await payment_dal.get_payment_by_db_id(session, payment.payment_id, fresh=True)
                or payment
            )
        payment = claimed_payment

        sale_mode = payment.sale_mode or (
            "traffic" if self.settings.traffic_sale_mode else "subscription"
        )
        payment_units = payment_units_for_activation(payment, sale_mode)
        outcome = await finalize_successful_payment(
            PaymentSuccessRequest(
                bot=self.bot,
                settings=self.settings,
                i18n=self.i18n,
                session=session,
                subscription_service=self.subscription_service,
                referral_service=self.referral_service,
                payment=payment,
                user_id=payment.user_id,
                amount=float(payment.amount),
                currency=str(payment.currency),
                sale_mode=sale_mode,
                months=payment_units,
                traffic_amount=float(payment_units),
                provider_subscription=str(getattr(payment, "provider", "") or WATA_PROVIDER),
                provider_notification=str(getattr(payment, "provider", "") or WATA_PROVIDER),
                db_user=payment.user,
                log_prefix=log_prefix,
            )
        )
        if outcome is None:
            return None
        return await payment_dal.get_payment_by_db_id(session, payment.payment_id) or payment

    def _paid_payload_matches_payment(
        self,
        payment: Any,
        payload: Mapping[str, Any],
        *,
        log_prefix: str,
    ) -> bool:
        amount = payload.get("amount")
        currency = payload.get("currency")
        if payment_amount_and_currency_match(
            expected_amount=payment.amount,
            expected_currency=payment.currency,
            received_amount=amount,
            received_currency=currency,
            allow_overpayment=True,
        ):
            return True
        logger.warning(
            "%s: amount or currency mismatch for payment %s (expected=%s %s, got=%s %s)",
            log_prefix,
            payment.payment_id,
            payment.amount,
            payment.currency,
            amount,
            currency,
        )
        return False

    async def _mark_declined_from_payload(
        self,
        session: AsyncSession,
        payment: Any,
        payload: Mapping[str, Any],
        *,
        log_prefix: str,
        notify_user: bool,
    ) -> Any | None:
        transaction_id = _wata_transaction_id(payload) or str(payment.payment_id)
        try:
            await payment_dal.update_provider_payment_and_status(
                session,
                payment.payment_id,
                transaction_id,
                "failed",
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception(
                "%s: failed to mark payment %s as failed.",
                log_prefix,
                transaction_id,
            )
            return None

        if notify_user:
            await notify_user_payment_failed(
                bot=self.bot,
                settings=self.settings,
                i18n=self.i18n,
                session=session,
                payment=payment,
            )
        return await payment_dal.get_payment_by_db_id(session, payment.payment_id) or payment

    def _local_payment_link_ttl_expired(self, payment: Any) -> bool:
        profile = self.profile_for_payment(payment)
        created_at = getattr(payment, "created_at", None)
        created_dt: datetime | None
        if isinstance(created_at, datetime):
            created_dt = (
                created_at.replace(tzinfo=UTC)
                if created_at.tzinfo is None
                else created_at.astimezone(UTC)
            )
        else:
            created_dt = _parse_wata_datetime(created_at)
        if created_dt is None:
            return False
        expires_at = created_dt + timedelta(minutes=profile.link_ttl_minutes)
        return expires_at <= datetime.now(UTC)

    async def _expired_link_payload_for_payment(self, payment: Any) -> Mapping[str, Any] | None:
        profile = self.profile_for_payment(payment)
        if not self.profile_enabled(profile.provider):
            return None
        provider_payment_id = str(getattr(payment, "provider_payment_id", "") or "").strip()
        if not provider_payment_id:
            return None

        success, data = await self.get_payment_link(provider_payment_id, profile=profile)
        if not success or not isinstance(data, dict):
            status_code = data.get("status") if isinstance(data, dict) else None
            if status_code == 404 and self._local_payment_link_ttl_expired(payment):
                return {"id": provider_payment_id}
            return None

        expiration_raw = data.get("expirationDateTime") or data.get("expiration_date_time")
        expiration_dt = _parse_wata_datetime(expiration_raw)
        if expiration_dt is None:
            return None
        if expiration_dt > datetime.now(UTC):
            return None
        return data

    async def _mark_expired_link(
        self,
        session: AsyncSession,
        payment: Any,
        payload: Mapping[str, Any],
        *,
        log_prefix: str,
    ) -> Any | None:
        provider_payment_id = (
            first_value(payload, "id", "paymentLinkId", "payment_link_id")
            or getattr(payment, "provider_payment_id", None)
            or str(payment.payment_id)
        )
        try:
            await payment_dal.update_provider_payment_and_status(
                session,
                payment.payment_id,
                str(provider_payment_id),
                "canceled",
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception(
                "%s: failed to mark expired payment link %s as canceled.",
                log_prefix,
                provider_payment_id,
            )
            return None
        return await payment_dal.get_payment_by_db_id(session, payment.payment_id) or payment

    async def refresh_payment_status(self, session: AsyncSession, payment: Any) -> Any:
        provider = str(getattr(payment, "provider", "") or "").strip().lower()
        if provider not in {WATA_PROVIDER, WATA_CRYPTO_PROVIDER}:
            return payment
        if not self.profile_enabled(provider):
            return payment

        current_status = str(getattr(payment, "status", "") or "").lower()
        if current_status == "succeeded" or current_status in {
            "failed",
            "canceled",
            "cancelled",
            "failed_creation",
        }:
            return payment

        final_payload = await self._find_final_transaction_for_payment(payment)
        final_status = _normalized_wata_status(final_payload)
        if final_payload and final_status == "paid":
            refreshed = await self._mark_paid_from_payload(
                session,
                payment,
                final_payload,
                log_prefix="Wata status refresh",
            )
            return refreshed or payment

        if final_payload and final_status == "declined":
            refreshed = await self._mark_declined_from_payload(
                session,
                payment,
                final_payload,
                log_prefix="Wata status refresh",
                notify_user=False,
            )
            return refreshed or payment

        expired_link_payload = await self._expired_link_payload_for_payment(payment)
        if expired_link_payload:
            refreshed = await self._mark_expired_link(
                session,
                payment,
                expired_link_payload,
                log_prefix="Wata status refresh",
            )
            return refreshed or payment

        return payment

    async def webhook_route(self, request: web.Request) -> web.Response:
        if not self.configured:
            return web.Response(status=503, text="wata_disabled")

        trusted = self.config.trusted_ips_list
        ip_check = check_webhook_source_ip(
            request,
            trusted_ips=trusted,
            trusted_proxies=self.settings.trusted_proxies,
            allow_empty=True,
        )
        if not ip_check.allowed:
            logger.warning(
                "Wata webhook denied from unauthorized IP source "
                "(client_ip=%s remote=%s x_forwarded_for=%s).",
                ip_check.client_ip,
                request.remote,
                request.headers.get("X-Forwarded-For"),
            )
            return web.Response(status=403, text="forbidden")

        raw_body = await request.read()
        profile_hint = self._profile_hint_from_raw_body(raw_body)
        if self.verify_webhook_signature:
            signature = request.headers.get("X-Signature", "")
            if not await self._verify_signature(raw_body, signature, profile=profile_hint):
                return web.Response(status=403, text="invalid_signature")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            logger.exception("Wata webhook: failed to parse JSON.")
            return web.Response(status=400, text="bad_request")

        transaction_id = str(payload.get("transactionId") or "").strip()
        payment_link_id = str(payload.get("paymentLinkId") or payload.get("id") or "").strip()
        status = str(payload.get("transactionStatus") or "").strip().lower()
        order_id_raw = payload.get("orderId")

        if not status or not (transaction_id or order_id_raw or payment_link_id):
            logger.error("Wata webhook: missing transaction status or ids: %s", payload)
            return web.Response(status=400, text="missing_fields")

        async with self.async_session_factory() as session:
            expected_providers = (
                profile_hint.provider if profile_hint else (WATA_PROVIDER, WATA_CRYPTO_PROVIDER)
            )
            payment = await lookup_payment_by_order_or_provider_id(
                session,
                providers=expected_providers,
                order_id_raw=order_id_raw,
                provider_payment_id=transaction_id or None,
            )
            if not payment and payment_link_id:
                payment = await lookup_payment_by_order_or_provider_id(
                    session,
                    providers=expected_providers,
                    provider_payment_id=payment_link_id,
                )
            if not payment:
                logger.error(
                    "Wata webhook: payment not found "
                    "(order_id=%s, transaction_id=%s, payment_link_id=%s)",
                    order_id_raw,
                    transaction_id,
                    payment_link_id,
                )
                return web.Response(status=404, text="payment_not_found")

            profile = self.profile_for_payment(payment)
            if profile_hint and profile_hint.provider != profile.provider:
                logger.warning(
                    "Wata webhook profile mismatch: payment_provider=%s terminal_provider=%s",
                    profile.provider,
                    profile_hint.provider,
                )
                return web.Response(status=403, text="terminal_mismatch")
            if self.verify_webhook_signature and profile_hint is None:
                signature = request.headers.get("X-Signature", "")
                if not await self._verify_signature(raw_body, signature, profile=profile):
                    return web.Response(status=403, text="invalid_signature")
            if not self._payload_matches_profile(payload, profile):
                return web.Response(status=403, text="terminal_mismatch")

            if payment.status == "succeeded":
                return web.Response(text="ok")

            if status in _WATA_IN_PROGRESS_STATUSES:
                if transaction_id and payment.provider_payment_id != transaction_id:
                    try:
                        await payment_dal.update_provider_payment_and_status(
                            session,
                            payment.payment_id,
                            transaction_id,
                            payment.status,
                        )
                        await session.commit()
                    except Exception:
                        await session.rollback()
                        logger.exception(
                            "Wata webhook: failed to persist transaction id %s for payment %s.",
                            transaction_id,
                            payment.payment_id,
                        )
                        return web.Response(status=500, text="processing_error")
                return web.Response(text="ok")

            if status == "paid":
                if not self._paid_payload_matches_payment(
                    payment,
                    payload,
                    log_prefix="Wata webhook",
                ):
                    return web.Response(status=400, text="amount_mismatch")
                if not await self._mark_paid_from_payload(
                    session,
                    payment,
                    payload,
                    log_prefix="Wata webhook",
                ):
                    return web.Response(status=500, text="processing_error")
                return web.Response(text="ok")

            if status == "declined":
                if not await self._mark_declined_from_payload(
                    session,
                    payment,
                    payload,
                    log_prefix="Wata webhook",
                    notify_user=True,
                ):
                    return web.Response(status=500, text="processing_error")
                return web.Response(text="ok")

            logger.warning(
                "Wata webhook: unhandled status '%s' for transaction %s",
                status,
                transaction_id,
            )
            return web.Response(text="status_ignored")
