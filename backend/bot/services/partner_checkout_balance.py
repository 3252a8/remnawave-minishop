from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra import events
from bot.infra.event_payloads import PartnerBalanceSpentPayload
from bot.services.partner_common import (
    PartnerError,
    amount_to_minor,
    currency_scale,
    minor_to_decimal_string,
)
from config.settings import Settings
from db.dal import partner_dal
from db.partner_models import PartnerLedgerEntry

TERMINAL_CHECKOUT_STATUSES = frozenset(
    {
        "activation_failed",
        "canceled",
        "cancelled",
        "expired",
        "failed",
        "failed_creation",
        "refunded",
        "reversed",
        "void",
    }
)


@dataclass(frozen=True, slots=True)
class PartnerCheckoutBalanceAllocation:
    partner_id: int
    currency: str
    currency_scale: int
    checkout_total_minor: int
    applied_minor: int

    @property
    def external_minor(self) -> int:
        return self.checkout_total_minor - self.applied_minor

    @property
    def checkout_total_amount(self) -> float:
        return float(
            minor_to_decimal_string(
                self.checkout_total_minor,
                scale=self.currency_scale,
            )
        )

    @property
    def external_amount(self) -> float:
        return float(
            minor_to_decimal_string(
                self.external_minor,
                scale=self.currency_scale,
            )
        )


def _normalized_status(value: Any) -> str:
    return str(value or "").strip().lower()


class PartnerCheckoutBalanceService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def quote(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        currency: str,
        checkout_total: Any,
        minimum_external_amount: Any = 0,
    ) -> PartnerCheckoutBalanceAllocation:
        config = self.settings.partner_settings
        if not config.enabled:
            raise PartnerError("partner_program_disabled", 403)
        if not config.balance_payment_enabled:
            raise PartnerError("partner_balance_payment_disabled", 403)

        normalized_currency = str(currency or "").strip().upper()
        scale = currency_scale(normalized_currency)
        total_minor = amount_to_minor(checkout_total, scale=scale)
        minimum_external_minor = max(
            0,
            amount_to_minor(minimum_external_amount, scale=scale),
        )
        if total_minor <= 0:
            raise PartnerError("partner_balance_zero_amount", 400)

        profile = await partner_dal.get_profile_by_user_id(
            session,
            user_id,
            for_update=True,
        )
        if profile is None:
            raise PartnerError("partner_not_found", 404)
        if str(profile.status) != "active":
            raise PartnerError("partner_not_active", 403)

        available_minor = max(
            0,
            await partner_dal.balance_minor(
                session,
                int(profile.partner_id),
                normalized_currency,
            ),
        )
        if available_minor <= 0:
            raise PartnerError("insufficient_partner_balance", 409)

        # A fully covered checkout does not call an external provider.  For a
        # mixed checkout keep the provider's declared minimum payable amount
        # intact instead of creating an invoice the provider will reject.
        maximum_applied_minor = (
            total_minor
            if available_minor >= total_minor
            else max(0, total_minor - minimum_external_minor)
        )
        applied_minor = min(available_minor, maximum_applied_minor)
        if applied_minor <= 0:
            raise PartnerError("partner_balance_below_provider_minimum", 409)

        return PartnerCheckoutBalanceAllocation(
            partner_id=int(profile.partner_id),
            currency=normalized_currency,
            currency_scale=scale,
            checkout_total_minor=total_minor,
            applied_minor=applied_minor,
        )

    @staticmethod
    async def reserve(
        session: AsyncSession,
        *,
        payment_id: int,
        allocation: PartnerCheckoutBalanceAllocation,
    ) -> PartnerLedgerEntry:
        key = f"checkout-spend:{payment_id}"
        existing = await partner_dal.get_ledger_entry_by_key(session, key)
        if existing is not None:
            if (
                int(existing.partner_id) != allocation.partner_id
                or str(existing.currency).upper() != allocation.currency
                or int(existing.amount_minor) != -allocation.applied_minor
            ):
                raise PartnerError("partner_balance_reservation_conflict", 409)
            return existing

        profile = await partner_dal.get_profile_by_id(
            session,
            allocation.partner_id,
            for_update=True,
        )
        if profile is None or str(profile.status) != "active":
            raise PartnerError("partner_not_active", 403)
        available_minor = await partner_dal.balance_minor(
            session,
            allocation.partner_id,
            allocation.currency,
        )
        if available_minor < allocation.applied_minor:
            raise PartnerError("insufficient_partner_balance", 409)

        entry = await partner_dal.create_ledger_entry(
            session,
            partner_id=allocation.partner_id,
            currency=allocation.currency,
            currency_scale=allocation.currency_scale,
            amount_minor=-allocation.applied_minor,
            kind="checkout_spend",
            state="posted",
            reference_type="payment",
            reference_id=str(payment_id),
            idempotency_key=key,
            posted_at=datetime.now(UTC),
        )
        await events.emit_model(
            PartnerBalanceSpentPayload(
                partner_id=allocation.partner_id,
                payment_db_id=payment_id,
                currency=allocation.currency,
                amount_minor=allocation.applied_minor,
                spent_at=datetime.now(UTC),
            )
        )
        return entry

    @staticmethod
    async def release(
        session: AsyncSession,
        *,
        payment_id: int,
        reason: str,
    ) -> PartnerLedgerEntry | None:
        spend = await partner_dal.get_ledger_entry_by_key(
            session,
            f"checkout-spend:{payment_id}",
        )
        if spend is None:
            return None
        await partner_dal.get_profile_by_id(
            session,
            int(spend.partner_id),
            for_update=True,
        )
        key = f"checkout-spend-release:{payment_id}"
        existing = await partner_dal.get_ledger_entry_by_key(session, key)
        if existing is not None:
            if str(existing.state) == "void":
                existing.state = "posted"
                existing.reason = reason.strip() or "checkout payment released"
            return existing
        return await partner_dal.create_ledger_entry(
            session,
            partner_id=int(spend.partner_id),
            currency=str(spend.currency),
            currency_scale=int(spend.currency_scale),
            amount_minor=-int(spend.amount_minor),
            kind="checkout_spend_release",
            state="posted",
            reference_type="payment",
            reference_id=str(payment_id),
            idempotency_key=key,
            reason=reason.strip() or "checkout payment released",
            posted_at=datetime.now(UTC),
        )

    @staticmethod
    async def ensure_consumed(
        session: AsyncSession,
        *,
        payment_id: int,
    ) -> PartnerLedgerEntry | None:
        """Undo an earlier release when a delayed success arrives.

        Keeping the original debit and voiding its compensating credit makes
        retries idempotent.  If the returned funds were already spent, the
        balance becomes negative instead of duplicating money.
        """

        release = await partner_dal.get_ledger_entry_by_key(
            session,
            f"checkout-spend-release:{payment_id}",
        )
        if release is None:
            return None
        await partner_dal.get_profile_by_id(
            session,
            int(release.partner_id),
            for_update=True,
        )
        if str(release.state) == "posted":
            release.state = "void"
            release.reason = "checkout payment completed after balance release"
        return release

    @classmethod
    async def release_if_terminal(
        cls,
        session: AsyncSession,
        *,
        payment_id: int,
        status: Any,
    ) -> PartnerLedgerEntry | None:
        normalized = _normalized_status(status)
        if normalized not in TERMINAL_CHECKOUT_STATUSES:
            return None
        return await cls.release(
            session,
            payment_id=payment_id,
            reason=f"checkout payment {normalized}",
        )


def provider_minimum_amount(metadata: Any) -> Decimal:
    if not isinstance(metadata, Mapping):
        return Decimal("0")
    values: list[Decimal] = []
    for key in ("min_amount", "minimum_amount", "shop_min_amount"):
        value = metadata.get(key)
        if value in (None, ""):
            continue
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if parsed.is_finite() and parsed > 0:
            values.append(parsed)
    return max(values, default=Decimal("0"))
