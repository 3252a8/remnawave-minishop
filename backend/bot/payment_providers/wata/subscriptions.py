"""Provider-managed recurring payments for Wata subscriptions.

Wata owns the schedule and reports each debit as a ``Token`` transaction.
Core stores only attribution and immutable checkout terms; payer contact data is
sent while creating the first payment link and is never persisted locally.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from config.subscription_periods import legacy_months_to_days, sale_mode_duration_days
from db.dal import payment_dal, subscription_dal, user_dal, wata_subscription_dal
from db.models import Payment, WataSubscription

from ..shared import (
    PaymentSuccessRequest,
    build_payment_description,
    build_payment_record_payload,
    finalize_successful_payment,
    lookup_payment_by_order_or_provider_id,
    make_translator,
    payment_amount_and_currency_match,
    payment_units_for_activation,
    post_json_request,
    sale_mode_base,
)
from .config import (
    WATA_PROVIDER,
    WataTerminalProfile,
    _normalized_wata_status,
    _parse_wata_datetime,
    _wata_success_status,
    _wata_transaction_id,
)

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService

logger = logging.getLogger(__name__)

_PHONE_SEPARATORS = re.compile(r"[\s()\-.]")
_E164_PHONE = re.compile(r"^\+[1-9]\d{7,14}$")
_STOPPED_STATUSES = {"completed", "failed"}


def normalize_subscription_phone(value: Any) -> str | None:
    normalized = _PHONE_SEPARATORS.sub("", str(value or "").strip())
    if normalized.startswith("00"):
        normalized = f"+{normalized[2:]}"
    if not normalized.startswith("+") and normalized.isdigit():
        normalized = f"+{normalized}"
    return normalized if _E164_PHONE.fullmatch(normalized) else None


def subscription_terms_for_checkout(months: Any, sale_mode: str) -> tuple[int, str] | None:
    """Map a Core subscription period to Wata's Week/Month schedule."""

    if sale_mode_base(str(sale_mode or "")) != "subscription":
        return None
    duration_days = sale_mode_duration_days(str(sale_mode or ""))
    try:
        units_float = float(months)
        units = int(units_float)
    except (TypeError, ValueError):
        units_float = 0.0
        units = 0
    if units <= 0 or units_float != units:
        if duration_days is not None and duration_days % 7 == 0:
            return duration_days // 7, "Week"
        return None
    if duration_days is None or duration_days == legacy_months_to_days(units):
        return units, "Month"
    if duration_days % 7 == 0:
        return duration_days // 7, "Week"
    return None


def subscription_context_supported(config: Any, months: Any, sale_mode: str) -> bool:
    return subscription_terms_for_checkout(months, sale_mode) is not None


def subscription_promo_supported(config: Any, months: Any, sale_mode: str, promo: Any) -> bool:
    # Wata repeats the first link amount, while checkout discounts are one-off.
    return False


def subscription_charge_key(subscription_id: str, transaction_id: str) -> str:
    return f"wata-sub:{subscription_id}:{transaction_id}"


def subscription_bundle_supported(value: str | None) -> bool:
    """Reject first-period proration that Wata would repeat forever."""

    if not value:
        return True
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            return False
        try:
            immediate_amount = float(item.get("immediate_amount") or 0)
            immediate_stars = int(item.get("immediate_stars_amount") or 0)
            amount = float(item.get("amount") or 0)
            future_amount = float(item.get("future_amount") or 0)
        except (TypeError, ValueError):
            return False
        if abs(immediate_amount) > 1e-9 or immediate_stars != 0:
            return False
        if abs(amount - future_amount) > 1e-9:
            return False
    return True


def renewal_bundle_snapshot(value: str | None, active: Any | None) -> str | None:
    """Refresh only the concurrency guard while preserving authorized limits and prices."""

    if not value:
        return None
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("invalid checkout bundle snapshot")
    items = payload.get("items") or []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("invalid checkout bundle item")
        item["amount"] = float(item.get("future_amount") or 0)
        item["stars_amount"] = int(item.get("future_stars_amount") or 0)
        item["immediate_amount"] = 0.0
        item["immediate_stars_amount"] = 0
        item["immediate_applies"] = False
    payload["addons_amount"] = round(
        sum(float(item.get("future_amount") or 0) for item in items), 8
    )
    payload["addons_stars"] = sum(int(item.get("future_stars_amount") or 0) for item in items)
    payload["active_context"] = (
        {
            "subscription_id": int(active.subscription_id),
            "tariff_key": str(active.tariff_key or ""),
            "end_at": active.end_date.isoformat(),
        }
        if active is not None and getattr(active, "end_date", None) is not None
        else None
    )
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class WataSubscriptionRuntime:
    bot: Any
    settings: Any
    config: Any
    i18n: Any
    async_session_factory: Any
    subscription_service: SubscriptionService
    referral_service: ReferralService

    if TYPE_CHECKING:

        @property
        def base_url(self) -> str: ...

        async def _get_session(self) -> Any: ...

        def profile_for_method(self, method: Any = WATA_PROVIDER) -> WataTerminalProfile: ...

        def _auth_headers(self, profile: WataTerminalProfile | None = None) -> dict[str, str]: ...

        def _payload_matches_profile(
            self, payload: Mapping[str, Any], profile: WataTerminalProfile
        ) -> bool: ...

        async def _mark_paid_from_payload(
            self,
            session: AsyncSession,
            payment: Any,
            payload: Mapping[str, Any],
            *,
            log_prefix: str,
        ) -> Any | None: ...


class WataSubscriptionMixin(WataSubscriptionRuntime):
    @property
    def subscriptions_enabled(self) -> bool:
        return bool(
            self.profile_for_method(WATA_PROVIDER).configured
            and (self.config.SUBSCRIPTION_ENABLED or self.config.SUBSCRIPTION_ADMIN_ONLY_ENABLED)
        )

    @property
    def manages_recurrence(self) -> bool:
        # Cancellation must remain available after the checkout button is hidden.
        return bool(self.profile_for_method(WATA_PROVIDER).configured)

    async def get_remote_subscription(
        self,
        subscription_id: str,
    ) -> tuple[bool, dict[str, Any]]:
        remote_id = str(subscription_id or "").strip()
        if not self.manages_recurrence or not remote_id:
            return False, {"message": "service_not_configured"}
        session = await self._get_session()
        profile = self.profile_for_method(WATA_PROVIDER)
        try:
            async with session.get(
                f"{self.base_url}/subscriptions/{remote_id}",
                headers=self._auth_headers(profile),
            ) as response:
                body = await response.text()
                data = await response.json(content_type=None) if body else {}
                if not _wata_success_status(response.status, data) or not isinstance(data, dict):
                    return False, {"status": response.status, "message": data}
                return True, data
        except Exception as exc:
            logger.exception("Wata get_subscription failed: id=%s", remote_id)
            return False, {"message": str(exc)}

    async def complete_remote_subscription(self, subscription_id: str) -> bool:
        remote_id = str(subscription_id or "").strip()
        if not self.manages_recurrence or not remote_id:
            return False
        session = await self._get_session()
        profile = self.profile_for_method(WATA_PROVIDER)
        success, _data = await post_json_request(
            session,
            f"{self.base_url}/subscriptions/{remote_id}/statuses",
            body={"status": "Completed"},
            headers=self._auth_headers(profile),
            log_prefix="Wata complete_subscription",
            is_success=_wata_success_status,
        )
        return success

    async def cancel_provider_recurrence(
        self,
        session: AsyncSession,
        *,
        user_id: int,
    ) -> bool:
        records = await wata_subscription_dal.list_live_for_user(session, int(user_id))
        all_completed = True
        for record in records:
            if await self.complete_remote_subscription(str(record.wata_subscription_id)):
                await wata_subscription_dal.mark_status(session, record, "completed")
            else:
                all_completed = False
        return all_completed

    async def handle_subscription_status(
        self,
        payload: Mapping[str, Any],
        *,
        profile: WataTerminalProfile,
    ) -> web.Response:
        if not self._payload_matches_profile(payload, profile):
            return web.Response(status=403, text="terminal_mismatch")
        subscription_id = str(payload.get("subscriptionId") or "").strip()
        status = str(payload.get("status") or "").strip().lower()
        if not subscription_id or status not in {"active", *_STOPPED_STATUSES}:
            return web.Response(status=400, text="missing_fields")

        async with self.async_session_factory() as session:
            record = await wata_subscription_dal.get_subscription(
                session, subscription_id, for_update=True
            )
            if record is None:
                record = await self._mirror_from_remote(session, subscription_id)
            if record is None:
                await session.rollback()
                await self.complete_remote_subscription(subscription_id)
                return web.Response(status=404, text="subscription_not_found")
            await wata_subscription_dal.mark_status(session, record, status)
            await self._mirror_local_auto_renew(
                session,
                record,
                enabled=status == "active",
            )
            await session.commit()
        return web.Response(text="ok")

    async def handle_subscription_transaction(
        self,
        payload: Mapping[str, Any],
        *,
        profile: WataTerminalProfile,
    ) -> web.Response:
        if not self._payload_matches_profile(payload, profile):
            return web.Response(status=403, text="terminal_mismatch")
        subscription_id = str(payload.get("subscriptionId") or "").strip()
        transaction_id = _wata_transaction_id(payload)
        status = _normalized_wata_status(payload)
        if not subscription_id or not transaction_id or not status:
            return web.Response(status=400, text="missing_fields")

        async with self.async_session_factory() as session:
            record = await wata_subscription_dal.get_subscription(
                session, subscription_id, for_update=True
            )
            if record is None:
                record = await self._mirror_from_payload(session, subscription_id, payload)
            if record is None:
                await session.rollback()
                await self.complete_remote_subscription(subscription_id)
                return web.Response(status=404, text="subscription_not_found")
            if not payment_amount_and_currency_match(
                expected_amount=record.amount,
                expected_currency=record.currency,
                received_amount=payload.get("amount"),
                received_currency=payload.get("currency"),
            ):
                return web.Response(status=400, text="amount_mismatch")
            if status != "paid":
                return web.Response(text="ok")

            existing = await payment_dal.get_payment_by_provider_payment_id(
                session, WATA_PROVIDER, transaction_id
            )
            if existing is not None and str(existing.status or "").lower() == "succeeded":
                await session.commit()
                replaced = await self._cancel_superseded_subscriptions(record)
                return (
                    web.Response(text="ok")
                    if replaced
                    else web.Response(status=500, text="replacement_incomplete")
                )

            if int(record.charges_count or 0) == 0:
                response = await self._settle_initial_charge(
                    session, record, payload, transaction_id
                )
            else:
                response = await self._settle_renewal_charge(
                    session, record, payload, transaction_id
                )
        return response

    async def _mirror_from_payload(
        self,
        session: AsyncSession,
        subscription_id: str,
        payload: Mapping[str, Any],
    ) -> WataSubscription | None:
        order_id = payload.get("orderId")
        anchor = await lookup_payment_by_order_or_provider_id(
            session,
            providers=WATA_PROVIDER,
            order_id_raw=order_id,
        )
        return await self._create_mirror(session, subscription_id, anchor)

    async def _mirror_from_remote(
        self,
        session: AsyncSession,
        subscription_id: str,
    ) -> WataSubscription | None:
        success, remote = await self.get_remote_subscription(subscription_id)
        if not success:
            return None
        anchor = await lookup_payment_by_order_or_provider_id(
            session,
            providers=WATA_PROVIDER,
            order_id_raw=remote.get("orderId"),
        )
        return await self._create_mirror(session, subscription_id, anchor)

    async def _create_mirror(
        self,
        session: AsyncSession,
        subscription_id: str,
        anchor: Any,
    ) -> WataSubscription | None:
        if anchor is None or str(getattr(anchor, "provider", "")).lower() != WATA_PROVIDER:
            return None
        terms = subscription_terms_for_checkout(
            getattr(anchor, "subscription_duration_months", None),
            str(getattr(anchor, "sale_mode", "") or ""),
        )
        if terms is None:
            return None
        period, interval = terms
        try:
            return await wata_subscription_dal.create_from_anchor(
                session,
                subscription_id=subscription_id,
                anchor=anchor,
                interval=interval,
                period=period,
                max_periods=int(self.config.SUBSCRIPTION_MAX_PERIODS),
            )
        except ValueError:
            logger.exception("Wata subscription attribution mismatch: id=%s", subscription_id)
            return None

    async def _settle_initial_charge(
        self,
        session: AsyncSession,
        record: WataSubscription,
        payload: Mapping[str, Any],
        transaction_id: str,
    ) -> web.Response:
        anchor = await payment_dal.get_payment_by_db_id(session, int(record.anchor_payment_id))
        if anchor is None:
            return web.Response(status=404, text="payment_not_found")
        await wata_subscription_dal.record_charge(
            session,
            record,
            payment_id=transaction_id,
            charged_at=_parse_wata_datetime(payload.get("paymentDateTime")),
        )
        settled = await self._mark_paid_from_payload(
            session,
            anchor,
            payload,
            log_prefix="Wata subscription webhook",
        )
        if settled is None:
            return web.Response(status=500, text="processing_error")
        replaced = await self._cancel_superseded_subscriptions(record)
        await self._mirror_local_auto_renew_after_commit(
            str(record.wata_subscription_id), enabled=True
        )
        return (
            web.Response(text="ok")
            if replaced
            else web.Response(status=500, text="replacement_incomplete")
        )

    async def _settle_renewal_charge(
        self,
        session: AsyncSession,
        record: WataSubscription,
        payload: Mapping[str, Any],
        transaction_id: str,
    ) -> web.Response:
        db_user = await user_dal.get_user_by_id(session, int(record.user_id))
        if db_user is None:
            await session.rollback()
            await self.complete_remote_subscription(str(record.wata_subscription_id))
            return web.Response(status=404, text="user_not_found")
        language = str(
            getattr(db_user, "language_code", None) or self.settings.DEFAULT_LANGUAGE or "en"
        )
        sale_mode = str(record.sale_mode or "subscription")
        active = await subscription_dal.get_active_subscription_by_user_id(
            session, int(record.user_id)
        )
        payload_data = build_payment_record_payload(
            user_id=int(record.user_id),
            amount=float(record.amount),
            currency=str(record.currency),
            status="pending_wata",
            description=build_payment_description(
                make_translator(self.i18n, language),
                months=int(record.months or 1),
                sale_mode=sale_mode,
            ),
            months=int(record.months or 0),
            duration_days=record.duration_days,
            subscription_terms_snapshot=record.subscription_terms_snapshot,
            provider=WATA_PROVIDER,
            sale_mode=sale_mode,
            is_auto_renew=True,
            renewal_subscription_id=int(active.subscription_id) if active else None,
            checkout_bundle_snapshot=renewal_bundle_snapshot(
                record.checkout_bundle_snapshot,
                active,
            ),
        )
        payload_data.update(
            idempotence_key=subscription_charge_key(
                str(record.wata_subscription_id), transaction_id
            ),
            provider_payment_id=transaction_id,
            tariff_key=record.tariff_key,
        )
        payment, _created = await payment_dal.create_or_get_payment_record_by_idempotence_key(
            session, payload_data
        )
        claimed = await payment_dal.claim_payment_finalization(
            session,
            int(payment.payment_id),
            provider_payment_id=transaction_id,
        )
        if claimed is None:
            return web.Response(text="ok")
        await wata_subscription_dal.record_charge(
            session,
            record,
            payment_id=transaction_id,
            charged_at=_parse_wata_datetime(payload.get("paymentDateTime")),
        )
        outcome = await self._finalize_subscription_payment(session, claimed, record)
        return (
            web.Response(text="ok")
            if outcome is not None
            else web.Response(status=500, text="processing_error")
        )

    async def _cancel_superseded_subscriptions(self, record: WataSubscription) -> bool:
        """Keep the newly confirmed mandate and stop every older live one."""

        try:
            all_completed = True
            async with self.async_session_factory() as session:
                live = await wata_subscription_dal.list_live_for_user(session, int(record.user_id))
                for other in live:
                    if str(other.wata_subscription_id) == str(record.wata_subscription_id):
                        continue
                    logger.warning(
                        "Wata: replacing subscription %s with %s for user %s",
                        other.wata_subscription_id,
                        record.wata_subscription_id,
                        record.user_id,
                    )
                    if await self.complete_remote_subscription(str(other.wata_subscription_id)):
                        await wata_subscription_dal.mark_status(session, other, "completed")
                    else:
                        all_completed = False
                await session.commit()
            return all_completed
        except Exception:
            logger.exception(
                "Wata subscription %s could not retire superseded mandates",
                record.wata_subscription_id,
            )
            return False

    async def _finalize_subscription_payment(
        self,
        session: AsyncSession,
        payment: Payment,
        record: WataSubscription,
    ) -> Any:
        sale_mode = str(payment.sale_mode or record.sale_mode or "subscription")
        units = payment_units_for_activation(payment, sale_mode)
        return await finalize_successful_payment(
            PaymentSuccessRequest(
                bot=self.bot,
                settings=self.settings,
                i18n=self.i18n,
                session=session,
                subscription_service=self.subscription_service,
                referral_service=self.referral_service,
                payment=payment,
                user_id=int(payment.user_id),
                amount=float(payment.amount),
                currency=str(payment.currency),
                sale_mode=sale_mode,
                months=units,
                traffic_amount=float(units),
                provider_subscription=WATA_PROVIDER,
                provider_notification=WATA_PROVIDER,
                log_prefix="Wata subscription webhook",
            )
        )

    async def _mirror_local_auto_renew(
        self,
        session: AsyncSession,
        record: WataSubscription,
        *,
        enabled: bool,
    ) -> None:
        subscription = await subscription_dal.get_active_subscription_by_user_id(
            session, int(record.user_id)
        )
        if subscription is None or str(subscription.provider or "").lower() != WATA_PROVIDER:
            return
        if bool(subscription.auto_renew_enabled) == enabled:
            return
        await subscription_dal.set_auto_renew(
            session,
            int(subscription.subscription_id),
            enabled,
            stop_reason="provider_cancelled" if not enabled else "consent_changed",
        )

    async def _mirror_local_auto_renew_after_commit(
        self,
        subscription_id: str,
        *,
        enabled: bool,
    ) -> None:
        try:
            async with self.async_session_factory() as session:
                record = await wata_subscription_dal.get_subscription(
                    session, subscription_id, for_update=True
                )
                if record is None:
                    return
                await self._mirror_local_auto_renew(session, record, enabled=enabled)
                await session.commit()
        except Exception:
            logger.exception("Wata subscription %s local mirror failed", subscription_id)


__all__ = [
    "WataSubscriptionMixin",
    "normalize_subscription_phone",
    "renewal_bundle_snapshot",
    "subscription_bundle_supported",
    "subscription_charge_key",
    "subscription_context_supported",
    "subscription_promo_supported",
    "subscription_terms_for_checkout",
]
