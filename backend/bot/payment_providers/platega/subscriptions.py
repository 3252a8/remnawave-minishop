"""Platega recurring SBP subscriptions (``paymentMethod`` 6).

Platega owns the schedule. After the payer confirms the mandate we never
initiate a charge again: Platega debits the payer every interval and reports
every attempt on the same ``/webhook/platega`` route. That is the mirror image
of the saved-method providers (YooKassa, CloudPayments, Stripe), where our
renewal worker is the initiator, so the Platega specs deliberately do **not**
declare ``supports_recurring`` — enabling it would make the worker try to
charge a saved method that does not exist for any Platega customer. They
declare ``manages_recurring`` instead: the local ``auto_renew_enabled`` flag
only mirrors Platega's state, and turning it off cancels the mandate upstream.

Two callback shapes arrive here (https://docs.platega.io/):

* *charge* callbacks — one per debit attempt, carrying a fresh ``Id`` plus the
  ``SubscriptionId`` and ``NextChargeAt``;
* *subscription status* callbacks — ``SUBSCRIPTION_ACTIVATED`` /
  ``SUBSCRIPTION_PAST_DUE`` / ``SUBSCRIPTION_CANCELLED`` /
  ``SUBSCRIPTION_FAILED``, where ``Id`` is the subscription, not a transaction.

The published examples mix ``Id``/``id`` casing between the transaction and
subscription callbacks, so every field is read case-insensitively.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from aiogram import Bot
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from db.dal import payment_dal, platega_dal, subscription_dal, user_dal
from db.models import Payment, PlategaSubscription

from ..shared import (
    PaymentSuccessRequest,
    build_payment_description,
    build_payment_record_payload,
    finalize_successful_payment,
    make_translator,
    notify_user_payment_failed,
    payment_amount_and_currency_match,
    sale_mode_base,
)

if TYPE_CHECKING:
    from bot.services.referral_service import ReferralService
    from bot.services.subscription_service_impl.core import SubscriptionService
else:
    ReferralService = object
    SubscriptionService = object

logger = logging.getLogger(__name__)

PLATEGA_PROVIDER = "platega"
PLATEGA_PENDING_STATUS = "pending_platega"

# Platega documents ``paymentMethod: 6`` as the subscription product.
DEFAULT_SUBSCRIPTION_METHOD = 6

# Platega ``SubscriptionInterval``: 1=day, 2=week, 3=month, 4=year. Only whole
# month and year cycles can express a period tariff, so a 3- or 6-month plan
# has no representable mandate and the button stays hidden for it rather than
# silently billing the customer on the wrong cadence.
INTERVAL_MONTH = 3
INTERVAL_YEAR = 4
SUBSCRIPTION_INTERVAL_BY_MONTHS: dict[int, int] = {1: INTERVAL_MONTH, 12: INTERVAL_YEAR}

CHARGE_CONFIRMED = "CONFIRMED"
CHARGE_FAILED_STATUSES = frozenset({"CANCELED", "CANCELLED", "CHARGEBACKED"})

SUBSCRIPTION_ACTIVATED = "SUBSCRIPTION_ACTIVATED"
SUBSCRIPTION_PAST_DUE = "SUBSCRIPTION_PAST_DUE"
SUBSCRIPTION_STOPPED_STATUSES = frozenset(
    {"SUBSCRIPTION_CANCELLED", "SUBSCRIPTION_CANCELED", "SUBSCRIPTION_FAILED"}
)
SUBSCRIPTION_STATUSES = frozenset(
    {SUBSCRIPTION_ACTIVATED, SUBSCRIPTION_PAST_DUE, *SUBSCRIPTION_STOPPED_STATUSES}
)

_LOCAL_STATUS_BY_CALLBACK = {
    SUBSCRIPTION_ACTIVATED: "active",
    SUBSCRIPTION_PAST_DUE: "past_due",
    "SUBSCRIPTION_CANCELLED": "cancelled",
    "SUBSCRIPTION_CANCELED": "cancelled",
    "SUBSCRIPTION_FAILED": "failed",
}


def callback_value(data: Mapping[str, Any], *keys: str) -> Any:
    """Read a Platega callback field regardless of the key casing it arrived in."""
    lowered = {str(key).lower(): value for key, value in data.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value is not None and value != "":
            return value
    return None


def parse_callback_datetime(value: Any) -> datetime | None:
    """Parse Platega's ISO-8601 ``NextChargeAt`` (``Z`` suffix included)."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Platega subscription callback: unparsable timestamp %r", value)
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def subscription_interval_for_months(months: Any) -> int | None:
    """Map a purchased period onto a Platega interval, or ``None`` when it has none."""
    try:
        value = int(float(months))
    except (TypeError, ValueError):
        return None
    return SUBSCRIPTION_INTERVAL_BY_MONTHS.get(value)


def subscription_context_supported(config: Any, months: Any, sale_mode: str) -> bool:
    """Only period subscriptions with a representable interval can be a mandate.

    Traffic packages, HWID device slots and tariff upgrades are one-off
    purchases; charging them again every month would be plain wrong.
    """
    if sale_mode_base(str(sale_mode or "")) != "subscription":
        return False
    return subscription_interval_for_months(months) is not None


def subscription_promo_supported(
    config: Any,
    months: Any,
    sale_mode: str,
    promo: Any,
) -> bool:
    """Always False: a mandate repeats one amount, a promo discount is one-off.

    Letting a discounted checkout create the mandate would lock the discount in
    for every future period; letting the mandate charge full price would
    silently ignore the promo the customer applied.
    """
    return False


def charge_idempotence_key(subscription_id: str, charge_id: str) -> str:
    """Stable local key for one Platega debit attempt."""
    return f"platega-sub:{subscription_id}:{charge_id}"


class PlategaSubscriptionRuntime:
    """The ``PlategaService`` surface the subscription mixin builds on."""

    bot: Bot
    settings: Settings
    config: Any
    i18n: JsonI18n
    async_session_factory: sessionmaker
    subscription_service: SubscriptionService
    referral_service: ReferralService

    @property
    def configured(self) -> bool:
        raise NotImplementedError

    @property
    def base_url(self) -> str:
        raise NotImplementedError

    @property
    def _auth_headers(self) -> dict[str, str]:
        raise NotImplementedError

    async def _get_session(self) -> Any:
        raise NotImplementedError

    async def create_transaction(
        self,
        *,
        amount: float,
        currency: str | None,
        description: str,
        payload: str | None = None,
        payment_method: int | None = None,
        interval: int | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        raise NotImplementedError


class PlategaSubscriptionMixin(PlategaSubscriptionRuntime):
    """Recurring-mandate API calls and webhook handling for Platega."""

    @property
    def subscription_method(self) -> int:
        return int(getattr(self.config, "SUBSCRIPTION_METHOD", 0) or DEFAULT_SUBSCRIPTION_METHOD)

    @property
    def subscriptions_enabled(self) -> bool:
        return bool(
            getattr(self.config, "SUBSCRIPTION_ENABLED", False)
            or getattr(self.config, "SUBSCRIPTION_ADMIN_ONLY_ENABLED", False)
        )

    @property
    def manages_recurrence(self) -> bool:
        """True when Platega mandates are live for this deployment."""
        return bool(self.configured and self.subscriptions_enabled)

    # ------------------------------------------------------------------ API

    async def create_subscription(
        self,
        *,
        amount: float,
        currency: str | None,
        description: str,
        months: Any,
        payload: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        interval = subscription_interval_for_months(months)
        if interval is None:
            logger.error("Platega subscription: no interval for %s months", months)
            return False, {"message": "unsupported_subscription_interval", "months": months}
        return await self.create_transaction(
            amount=amount,
            currency=currency,
            description=description,
            payload=payload,
            payment_method=self.subscription_method,
            interval=interval,
        )

    async def get_remote_subscription(self, subscription_id: str) -> tuple[bool, dict[str, Any]]:
        remote_id = str(subscription_id or "").strip()
        if not self.configured or not remote_id:
            return False, {"message": "service_not_configured"}
        session = await self._get_session()
        try:
            async with session.get(
                f"{self.base_url}/subscription/{remote_id}",
                headers=self._auth_headers,
            ) as response:
                data = await response.json(content_type=None)
                if response.status != 200 or not isinstance(data, dict):
                    return False, {"status": response.status, "message": data}
                return True, data
        except Exception as exc:
            logger.exception("Platega get_subscription failed: id=%s", remote_id)
            return False, {"message": str(exc)}

    async def cancel_remote_subscription(self, subscription_id: str) -> bool:
        """Stop future debits at Platega. The endpoint is documented idempotent."""
        remote_id = str(subscription_id or "").strip()
        if not self.configured or not remote_id:
            return False
        session = await self._get_session()
        try:
            async with session.post(
                f"{self.base_url}/subscription/{remote_id}/cancel",
                headers=self._auth_headers,
                json={},
            ) as response:
                body = await response.text()
                if response.status != 200:
                    logger.error(
                        "Platega cancel_subscription failed: id=%s status=%s body=%s",
                        remote_id,
                        response.status,
                        body,
                    )
                    return False
                logger.info("Platega subscription %s cancelled", remote_id)
                return True
        except Exception:
            logger.exception("Platega cancel_subscription request failed: id=%s", remote_id)
            return False

    async def try_reuse_pending_subscription(self, payment: Any) -> str | None:
        """Reuse the mandate confirmation link while Platega still accepts it.

        The redirect is only valid until the payer confirms (Platega documents a
        30-minute window), so an unconfirmed mandate is re-offered and anything
        else forces a fresh one instead of showing a dead link.
        """
        subscription_id = str(getattr(payment, "provider_payment_id", None) or "").strip()
        payment_url = str(getattr(payment, "provider_payment_url", None) or "").strip()
        if not subscription_id or not payment_url:
            return None
        success, data = await self.get_remote_subscription(subscription_id)
        if not success:
            return None
        if str(data.get("status") or "").strip().lower() != "pendingagreement":
            return None
        return payment_url

    async def cancel_provider_recurrence(self, session: AsyncSession, *, user_id: int) -> bool:
        """Cancel every live mandate a customer owns.

        Called when the customer turns auto-renew off. Local state is only
        flipped for mandates Platega confirmed as cancelled, so a failed API
        call leaves the row live and the next attempt can retry it instead of
        pretending the customer is no longer billed.
        """
        records = await platega_dal.list_live_subscriptions_for_user(session, int(user_id))
        if not records:
            return True
        all_cancelled = True
        for record in records:
            remote_id = str(record.platega_subscription_id)
            if await self.cancel_remote_subscription(remote_id):
                await platega_dal.mark_status(session, record, "cancelled")
            else:
                all_cancelled = False
        await session.flush()
        return all_cancelled

    # -------------------------------------------------------------- webhook

    async def handle_subscription_status_callback(
        self,
        data: Mapping[str, Any],
    ) -> web.Response:
        subscription_id = str(
            callback_value(data, "SubscriptionId", "Id", "transactionId") or ""
        ).strip()
        status = str(callback_value(data, "Status") or "").upper()
        local_status = _LOCAL_STATUS_BY_CALLBACK.get(status)
        if not subscription_id or local_status is None:
            logger.error("Platega subscription status callback: unusable payload %s", data)
            return web.Response(status=400, text="missing_fields")

        next_charge_at = parse_callback_datetime(callback_value(data, "NextChargeAt"))
        async with self.async_session_factory() as session:
            record = await platega_dal.get_subscription(session, subscription_id, for_update=True)
            if record is None:
                record = await self._mirror_from_anchor(
                    session,
                    subscription_id=subscription_id,
                    status=local_status,
                    next_charge_at=next_charge_at,
                )
                if record is None:
                    await self._cancel_unattributable_subscription(subscription_id)
                    return web.Response(status=404, text="subscription_not_found")
            else:
                await platega_dal.mark_status(
                    session,
                    record,
                    local_status,
                    next_charge_at=next_charge_at,
                )

            if local_status == "active":
                await self._mirror_local_auto_renew(session, record, enabled=True)
            elif local_status in {"cancelled", "failed"}:
                await self._mirror_local_auto_renew(session, record, enabled=False)
            await session.commit()

        logger.info(
            "Platega subscription %s is now %s (next charge %s)",
            subscription_id,
            local_status,
            next_charge_at,
        )
        return web.Response(text="ok")

    async def handle_subscription_charge_callback(
        self,
        data: Mapping[str, Any],
    ) -> web.Response:
        subscription_id = str(callback_value(data, "SubscriptionId") or "").strip()
        charge_id = str(callback_value(data, "Id", "transactionId") or "").strip()
        status = str(callback_value(data, "Status") or "").upper()
        if not subscription_id or not charge_id or not status:
            logger.error("Platega subscription charge callback: unusable payload %s", data)
            return web.Response(status=400, text="missing_fields")

        next_charge_at = parse_callback_datetime(callback_value(data, "NextChargeAt"))
        amount_raw = callback_value(data, "Amount")
        currency = callback_value(data, "Currency")

        if status not in CHARGE_FAILED_STATUSES and status != CHARGE_CONFIRMED:
            logger.info(
                "Platega subscription %s charge %s reported '%s'; nothing to settle yet",
                subscription_id,
                charge_id,
                status,
            )
            return web.Response(status=202, text="status_ignored")

        async with self.async_session_factory() as session:
            record = await platega_dal.get_subscription(session, subscription_id, for_update=True)
            anchor = await payment_dal.get_payment_by_provider_payment_id(
                session,
                PLATEGA_PROVIDER,
                subscription_id,
            )
            if record is None and anchor is None:
                # Nothing local can be credited, and ignoring it would let
                # Platega keep debiting the payer forever.
                await self._cancel_unattributable_subscription(subscription_id)
                return web.Response(status=404, text="subscription_not_found")

            if status in CHARGE_FAILED_STATUSES:
                return await self._settle_failed_charge(
                    session,
                    record=record,
                    anchor=anchor,
                    subscription_id=subscription_id,
                    charge_id=charge_id,
                    status=status,
                    next_charge_at=next_charge_at,
                )
            return await self._settle_confirmed_charge(
                session,
                record=record,
                anchor=anchor,
                subscription_id=subscription_id,
                charge_id=charge_id,
                amount_raw=amount_raw,
                currency=currency,
                next_charge_at=next_charge_at,
            )

    # -------------------------------------------------------------- helpers

    async def _mirror_from_anchor(
        self,
        session: AsyncSession,
        *,
        subscription_id: str,
        status: str,
        next_charge_at: datetime | None,
    ) -> PlategaSubscription | None:
        """Create the local mandate mirror from the checkout that authorized it."""
        anchor = await payment_dal.get_payment_by_provider_payment_id(
            session,
            PLATEGA_PROVIDER,
            subscription_id,
        )
        if anchor is None:
            logger.error(
                "Platega subscription %s has no local checkout to attribute it to",
                subscription_id,
            )
            return None
        months = int(anchor.subscription_duration_months or 0)
        interval = subscription_interval_for_months(months)
        if interval is None:
            logger.error(
                "Platega subscription %s references %s months, which has no interval",
                subscription_id,
                months,
            )
            return None
        record = await platega_dal.upsert_subscription(
            session,
            platega_subscription_id=subscription_id,
            user_id=int(anchor.user_id),
            amount=float(anchor.amount),
            currency=str(anchor.currency),
            interval_code=interval,
            months=months,
            sale_mode=str(anchor.sale_mode or "subscription"),
            tariff_key=str(anchor.tariff_key) if anchor.tariff_key else None,
            status=status,
            next_charge_at=next_charge_at,
        )
        await self._cancel_superseded_mandates(session, record)
        return record

    async def _cancel_superseded_mandates(
        self,
        session: AsyncSession,
        record: PlategaSubscription,
    ) -> None:
        """Stop older mandates when a customer ends up with more than one.

        A customer who starts a second subscription before the first is
        cancelled would otherwise be debited twice per period. The newest
        mandate reflects their latest intent, so the older ones are cancelled
        upstream and the incident is logged for a human to refund if needed.
        """
        live = await platega_dal.list_live_subscriptions_for_user(session, int(record.user_id))
        superseded = [
            other
            for other in live
            if str(other.platega_subscription_id) != str(record.platega_subscription_id)
        ]
        for other in superseded:
            logger.error(
                "Platega: user %s now has mandate %s while %s was still live; "
                "cancelling the older one — review whether a refund is owed",
                record.user_id,
                record.platega_subscription_id,
                other.platega_subscription_id,
            )
            if await self.cancel_remote_subscription(str(other.platega_subscription_id)):
                await platega_dal.mark_status(session, other, "cancelled")

    async def _cancel_unattributable_subscription(self, subscription_id: str) -> None:
        logger.error(
            "Platega subscription %s is unknown locally; cancelling it upstream so the "
            "payer is not debited for an entitlement we cannot grant",
            subscription_id,
        )
        await self.cancel_remote_subscription(subscription_id)

    async def _mirror_local_auto_renew(
        self,
        session: AsyncSession,
        record: PlategaSubscription,
        *,
        enabled: bool,
    ) -> None:
        """Reflect the provider's recurrence state on the local subscription.

        Only Platega-funded entitlements are touched: a customer who switched
        to another provider must not lose their auto-renew flag because an old
        Platega mandate expired.
        """
        subscription = await subscription_dal.get_active_subscription_by_user_id(
            session,
            int(record.user_id),
        )
        if subscription is None:
            return
        if str(subscription.provider or "").strip().lower() != PLATEGA_PROVIDER:
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
                record = await platega_dal.get_subscription(
                    session,
                    subscription_id,
                    for_update=True,
                )
                if record is None:
                    return
                await self._mirror_local_auto_renew(session, record, enabled=enabled)
                await session.commit()
        except Exception:
            # The payment is already settled; a stale auto-renew flag must not
            # turn a successful charge into a webhook retry.
            logger.exception(
                "Platega subscription %s: failed to mirror the recurrence flag",
                subscription_id,
            )

    async def _settle_failed_charge(
        self,
        session: AsyncSession,
        *,
        record: PlategaSubscription | None,
        anchor: Payment | None,
        subscription_id: str,
        charge_id: str,
        status: str,
        next_charge_at: datetime | None,
    ) -> web.Response:
        first_charge = record is None or int(record.charges_count or 0) == 0
        if first_charge and anchor is not None and str(anchor.status or "").lower() != "succeeded":
            # The mandate was never confirmed: settle it exactly like a failed
            # one-off checkout so the customer gets the standard notice.
            try:
                await payment_dal.update_provider_payment_and_status(
                    session,
                    int(anchor.payment_id),
                    subscription_id,
                    "canceled",
                )
                if record is not None:
                    await platega_dal.mark_status(session, record, "cancelled")
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "Platega subscription %s: failed to cancel the initial payment",
                    subscription_id,
                )
                return web.Response(status=500, text="processing_error")
            await notify_user_payment_failed(
                bot=self.bot,
                settings=self.settings,
                i18n=self.i18n,
                session=session,
                payment=anchor,
            )
            return web.Response(text="ok_canceled")

        logger.warning(
            "Platega subscription %s charge %s failed with '%s' (next charge %s)",
            subscription_id,
            charge_id,
            status,
            next_charge_at,
        )
        if record is None:
            return web.Response(text="ok")
        # Platega drops ``NextChargeAt`` once it gives up on the mandate.
        stopped = next_charge_at is None
        await platega_dal.mark_status(
            session,
            record,
            "cancelled" if stopped else "past_due",
            next_charge_at=next_charge_at,
        )
        if stopped:
            await self._mirror_local_auto_renew(session, record, enabled=False)
        await session.commit()
        if anchor is not None:
            await notify_user_payment_failed(
                bot=self.bot,
                settings=self.settings,
                i18n=self.i18n,
                session=session,
                payment=anchor,
                message_key="payment_failed",
            )
        return web.Response(text="ok")

    async def _settle_confirmed_charge(
        self,
        session: AsyncSession,
        *,
        record: PlategaSubscription | None,
        anchor: Payment | None,
        subscription_id: str,
        charge_id: str,
        amount_raw: Any,
        currency: Any,
        next_charge_at: datetime | None,
    ) -> web.Response:
        idempotence_key = charge_idempotence_key(subscription_id, charge_id)
        already = await payment_dal.get_payment_by_idempotence_key(session, idempotence_key)
        if already is not None and str(already.status or "").lower() == "succeeded":
            return web.Response(text="ok")

        if record is None:
            record = await self._mirror_from_anchor(
                session,
                subscription_id=subscription_id,
                status="active",
                next_charge_at=next_charge_at,
            )
            if record is None:
                await self._cancel_unattributable_subscription(subscription_id)
                return web.Response(status=404, text="subscription_not_found")

        if not payment_amount_and_currency_match(
            expected_amount=record.amount,
            expected_currency=record.currency,
            received_amount=amount_raw,
            received_currency=currency,
            # Platega echoes the raw numeric amount the mandate was created
            # with, so the invoice precision is preserved.
            places=None,
            allow_overpayment=True,
        ):
            await session.rollback()
            logger.error(
                "Platega subscription %s charge %s does not match the mandate "
                "(expected=%s %s, got=%s %s)",
                subscription_id,
                charge_id,
                record.amount,
                record.currency,
                amount_raw,
                currency,
            )
            return web.Response(status=400, text="amount_mismatch")

        if int(record.charges_count or 0) == 0:
            return await self._settle_initial_charge(
                session,
                record=record,
                anchor=anchor,
                idempotence_key=idempotence_key,
                next_charge_at=next_charge_at,
            )
        return await self._settle_renewal_charge(
            session,
            record=record,
            idempotence_key=idempotence_key,
            charge_id=charge_id,
            next_charge_at=next_charge_at,
        )

    async def _settle_initial_charge(
        self,
        session: AsyncSession,
        *,
        record: PlategaSubscription,
        anchor: Payment | None,
        idempotence_key: str,
        next_charge_at: datetime | None,
    ) -> web.Response:
        """Credit the checkout that created the mandate.

        The anchor keeps ``provider_payment_id`` pointing at the subscription
        id — that is the only durable link renewals have back to the customer,
        so it must never be overwritten with a per-charge transaction id.
        """
        if anchor is None:
            logger.error(
                "Platega subscription %s lost its checkout payment before the first charge",
                record.platega_subscription_id,
            )
            return web.Response(status=404, text="payment_not_found")

        try:
            claimed = await payment_dal.claim_payment_finalization(
                session,
                int(anchor.payment_id),
                provider_payment_id=str(record.platega_subscription_id),
            )
        except Exception:
            await session.rollback()
            logger.exception(
                "Platega subscription %s: failed to claim the initial payment",
                record.platega_subscription_id,
            )
            return web.Response(status=500, text="processing_error")

        if claimed is None:
            # A transaction-status callback already credited this checkout.
            await platega_dal.record_charge(session, record, next_charge_at=next_charge_at)
            await self._mirror_local_auto_renew(session, record, enabled=True)
            await session.commit()
            return web.Response(text="ok")

        claimed.idempotence_key = idempotence_key
        subscription_id = str(record.platega_subscription_id)
        await platega_dal.record_charge(session, record, next_charge_at=next_charge_at)
        outcome = await self._finalize(session, payment=claimed, record=record)
        if outcome is None:
            return web.Response(status=500, text="processing_error")
        # The local entitlement only exists once finalization committed, so the
        # recurrence flag is mirrored in a follow-up transaction.
        await self._mirror_local_auto_renew_after_commit(subscription_id, enabled=True)
        return web.Response(text="ok")

    async def _settle_renewal_charge(
        self,
        session: AsyncSession,
        *,
        record: PlategaSubscription,
        idempotence_key: str,
        charge_id: str,
        next_charge_at: datetime | None,
    ) -> web.Response:
        db_user = await user_dal.get_user_by_id(session, int(record.user_id))
        if db_user is None:
            await session.rollback()
            logger.error(
                "Platega subscription %s belongs to a missing user %s",
                record.platega_subscription_id,
                record.user_id,
            )
            await self._cancel_unattributable_subscription(str(record.platega_subscription_id))
            return web.Response(status=404, text="user_not_found")

        language = str(
            getattr(db_user, "language_code", None) or self.settings.DEFAULT_LANGUAGE or "en"
        )
        sale_mode = str(record.sale_mode or "subscription")
        description = build_payment_description(
            make_translator(self.i18n, language),
            months=int(record.months),
            sale_mode=sale_mode,
        )
        active_subscription = await subscription_dal.get_active_subscription_by_user_id(
            session,
            int(record.user_id),
        )
        payload = build_payment_record_payload(
            user_id=int(record.user_id),
            amount=float(record.amount),
            currency=str(record.currency),
            status=PLATEGA_PENDING_STATUS,
            description=description,
            months=int(record.months),
            provider=PLATEGA_PROVIDER,
            sale_mode=sale_mode,
            is_auto_renew=True,
            renewal_subscription_id=(
                int(active_subscription.subscription_id) if active_subscription else None
            ),
        )
        payload["idempotence_key"] = idempotence_key
        payload["provider_payment_id"] = charge_id

        try:
            payment, _created = await payment_dal.create_or_get_payment_record_by_idempotence_key(
                session,
                payload,
            )
            claimed = await payment_dal.claim_payment_finalization(
                session,
                int(payment.payment_id),
                provider_payment_id=charge_id,
            )
        except Exception:
            await session.rollback()
            logger.exception(
                "Platega subscription %s: failed to open the renewal payment",
                record.platega_subscription_id,
            )
            return web.Response(status=500, text="processing_error")

        if claimed is None:
            await platega_dal.record_charge(session, record, next_charge_at=next_charge_at)
            await session.commit()
            return web.Response(text="ok")

        subscription_id = str(record.platega_subscription_id)
        await platega_dal.record_charge(session, record, next_charge_at=next_charge_at)
        outcome = await self._finalize(session, payment=claimed, record=record)
        if outcome is None:
            return web.Response(status=500, text="processing_error")
        await self._mirror_local_auto_renew_after_commit(subscription_id, enabled=True)
        return web.Response(text="ok")

    async def _finalize(
        self,
        session: AsyncSession,
        *,
        payment: Payment,
        record: PlategaSubscription,
    ) -> Any:
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
                sale_mode=str(payment.sale_mode or record.sale_mode or "subscription"),
                months=int(record.months),
                traffic_amount=float(record.months),
                provider_subscription=PLATEGA_PROVIDER,
                provider_notification=PLATEGA_PROVIDER,
                log_prefix="Platega subscription webhook",
            )
        )
