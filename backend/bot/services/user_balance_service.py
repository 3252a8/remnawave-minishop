from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.partner_commission_service import PartnerCommissionService
from bot.services.partner_common import (
    PartnerError,
    amount_to_minor,
    currency_scale,
    minor_to_decimal_string,
)
from config.settings import Settings
from db.balance_models import UserBalanceLedgerEntry
from db.dal import partner_dal, user_balance_dal, user_dal
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


class UserBalanceError(RuntimeError):
    def __init__(self, code: str, status: int = 400, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.status = status
        self.message = message


@dataclass(frozen=True, slots=True)
class UserBalanceAllocation:
    user_id: int
    currency: str
    currency_scale: int
    checkout_total_minor: int
    applied_minor: int

    @property
    def external_minor(self) -> int:
        return self.checkout_total_minor - self.applied_minor

    @property
    def checkout_total_amount(self) -> float:
        return float(minor_to_decimal_string(self.checkout_total_minor, scale=self.currency_scale))

    @property
    def external_amount(self) -> float:
        return float(minor_to_decimal_string(self.external_minor, scale=self.currency_scale))


def _entry_payload(
    entry: Any,
    *,
    source_id: Literal["user", "partner"],
) -> dict[str, Any]:
    return {
        "entry_id": int(entry.entry_id),
        "source_id": source_id,
        "amount_minor": int(entry.amount_minor),
        "kind": str(entry.kind),
        "state": str(entry.state),
        "reason": str(entry.reason) if entry.reason else None,
        "reference_type": str(entry.reference_type),
        "reference_id": str(entry.reference_id),
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


class UserBalanceService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def currency(self) -> str:
        return self.settings.balance_settings.currency

    @property
    def scale(self) -> int:
        return currency_scale(self.currency)

    async def snapshot(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        include_history: bool = False,
    ) -> dict[str, Any]:
        config = self.settings.balance_settings
        scale = currency_scale(config.currency)
        amount_minor = await user_balance_dal.balance_minor(session, user_id, config.currency)
        partner_minor = 0
        partner_available = False
        partner_adjustable = False
        partner_convertible = False
        partner_status: str | None = None
        partner_profile = None
        if self.settings.partner_settings.enabled:
            partner_profile = await partner_dal.get_profile_by_user_id(session, user_id)
            if partner_profile is not None:
                partner_adjustable = True
                partner_status = str(partner_profile.status)
                partner_minor = await partner_dal.balance_minor(
                    session,
                    int(partner_profile.partner_id),
                    config.currency,
                )
                if partner_status == "active":
                    partner_convertible = True
                    partner_available = bool(
                        self.settings.partner_settings.balance_payment_enabled and partner_minor > 0
                    )
        payload: dict[str, Any] = {
            "enabled": bool(config.enabled),
            "currency": config.currency,
            "currency_scale": scale,
            "amount_minor": amount_minor,
            "amount": minor_to_decimal_string(amount_minor, scale=scale),
            "topup_min_amount": config.topup_min_amount,
            "topup_max_amount": config.topup_max_amount,
            "topup_presets": config.topup_presets,
            "sources": [
                {
                    "id": "user",
                    "available": bool(config.enabled and amount_minor > 0),
                    "adjustable": True,
                    "amount_minor": amount_minor,
                    "amount": minor_to_decimal_string(amount_minor, scale=scale),
                    "currency": config.currency,
                },
                {
                    "id": "partner",
                    "available": partner_available,
                    "adjustable": partner_adjustable,
                    "convertible": partner_convertible,
                    "status": partner_status,
                    "amount_minor": partner_minor,
                    "amount": minor_to_decimal_string(partner_minor, scale=scale),
                    "currency": config.currency,
                },
            ],
        }
        if include_history:
            user_entries = await user_balance_dal.list_ledger_entries(
                session,
                user_id,
                currency=config.currency,
                limit=100,
            )
            history = [_entry_payload(entry, source_id="user") for entry in user_entries]
            if partner_profile is not None:
                partner_entries = await partner_dal.list_ledger_entries(
                    session,
                    int(partner_profile.partner_id),
                    currency=config.currency,
                    limit=100,
                )
                history.extend(
                    _entry_payload(entry, source_id="partner") for entry in partner_entries
                )
            history.sort(
                key=lambda item: (str(item.get("created_at") or ""), int(item["entry_id"])),
                reverse=True,
            )
            payload["history"] = history[:100]
        return payload

    async def quote(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        currency: str,
        checkout_total: Any,
        minimum_external_amount: Any = 0,
    ) -> UserBalanceAllocation:
        config = self.settings.balance_settings
        if not config.enabled:
            raise UserBalanceError("user_balance_disabled", 403)
        normalized_currency = str(currency or "").strip().upper()
        if normalized_currency != config.currency:
            raise UserBalanceError("user_balance_currency_mismatch", 409)
        scale = currency_scale(normalized_currency)
        total_minor = amount_to_minor(checkout_total, scale=scale)
        minimum_external_minor = max(0, amount_to_minor(minimum_external_amount, scale=scale))
        if total_minor <= 0:
            raise UserBalanceError("user_balance_zero_amount", 400)
        user = await user_dal.lock_user_by_id(session, user_id)
        if user is None or bool(user.is_banned):
            raise UserBalanceError("access_denied", 403)
        available_minor = max(
            0,
            await user_balance_dal.balance_minor(session, user_id, normalized_currency),
        )
        if available_minor <= 0:
            raise UserBalanceError("insufficient_user_balance", 409)
        maximum_applied_minor = (
            total_minor
            if available_minor >= total_minor
            else max(0, total_minor - minimum_external_minor)
        )
        applied_minor = min(available_minor, maximum_applied_minor)
        if applied_minor <= 0:
            raise UserBalanceError("user_balance_below_provider_minimum", 409)
        return UserBalanceAllocation(
            user_id=user_id,
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
        allocation: UserBalanceAllocation,
    ) -> UserBalanceLedgerEntry:
        key = f"user-balance-checkout-spend:{payment_id}"
        existing = await user_balance_dal.get_ledger_entry_by_key(session, key)
        if existing is not None:
            if (
                int(existing.user_id) != allocation.user_id
                or str(existing.currency).upper() != allocation.currency
                or int(existing.amount_minor) != -allocation.applied_minor
            ):
                raise UserBalanceError("user_balance_reservation_conflict", 409)
            return existing
        user = await user_dal.lock_user_by_id(session, allocation.user_id)
        if user is None or bool(user.is_banned):
            raise UserBalanceError("access_denied", 403)
        available_minor = await user_balance_dal.balance_minor(
            session,
            allocation.user_id,
            allocation.currency,
        )
        if available_minor < allocation.applied_minor:
            raise UserBalanceError("insufficient_user_balance", 409)
        return await user_balance_dal.create_ledger_entry(
            session,
            user_id=allocation.user_id,
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

    @staticmethod
    async def release(
        session: AsyncSession,
        *,
        payment_id: int,
        reason: str,
    ) -> UserBalanceLedgerEntry | None:
        spend = await user_balance_dal.get_ledger_entry_by_key(
            session,
            f"user-balance-checkout-spend:{payment_id}",
        )
        if spend is None:
            return None
        await user_dal.lock_user_by_id(session, int(spend.user_id))
        key = f"user-balance-checkout-spend-release:{payment_id}"
        existing = await user_balance_dal.get_ledger_entry_by_key(session, key)
        if existing is not None:
            if str(existing.state) == "void":
                existing.state = "posted"
                existing.reason = reason.strip() or "checkout payment released"
            return existing
        return await user_balance_dal.create_ledger_entry(
            session,
            user_id=int(spend.user_id),
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
    ) -> UserBalanceLedgerEntry | None:
        release = await user_balance_dal.get_ledger_entry_by_key(
            session,
            f"user-balance-checkout-spend-release:{payment_id}",
        )
        if release is None:
            return None
        await user_dal.lock_user_by_id(session, int(release.user_id))
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
    ) -> UserBalanceLedgerEntry | None:
        normalized = str(status or "").strip().lower()
        if normalized not in TERMINAL_CHECKOUT_STATUSES:
            return None
        return await cls.release(
            session,
            payment_id=payment_id,
            reason=f"checkout payment {normalized}",
        )

    async def credit_payment_topup(
        self,
        session: AsyncSession,
        *,
        payment_id: int,
        user_id: int,
        amount: Any,
        currency: str,
    ) -> UserBalanceLedgerEntry:
        normalized_currency = str(currency).strip().upper()
        scale = currency_scale(normalized_currency)
        amount_minor = amount_to_minor(amount, scale=scale)
        if amount_minor <= 0:
            raise UserBalanceError("user_balance_zero_amount", 400)
        user = await user_dal.lock_user_by_id(session, user_id)
        if user is None:
            raise UserBalanceError("user_not_found", 404)
        key = f"user-balance-payment-topup:{payment_id}"
        existing = await user_balance_dal.get_ledger_entry_by_key(session, key)
        if existing is not None:
            if (
                int(existing.user_id) != user_id
                or str(existing.currency).upper() != normalized_currency
                or int(existing.amount_minor) != amount_minor
                or str(existing.kind) != "payment_topup"
            ):
                raise UserBalanceError("user_balance_topup_conflict", 409)
            return existing
        return await user_balance_dal.create_ledger_entry(
            session,
            user_id=user_id,
            currency=normalized_currency,
            currency_scale=scale,
            amount_minor=amount_minor,
            kind="payment_topup",
            state="posted",
            reference_type="payment",
            reference_id=str(payment_id),
            idempotency_key=key,
            posted_at=datetime.now(UTC),
        )

    @staticmethod
    async def reverse_payment_topup(
        session: AsyncSession,
        *,
        payment_id: int,
        reason: str,
    ) -> UserBalanceLedgerEntry | None:
        credit = await user_balance_dal.get_ledger_entry_by_key(
            session,
            f"user-balance-payment-topup:{payment_id}",
        )
        if credit is None:
            return None
        await user_dal.lock_user_by_id(session, int(credit.user_id))
        key = f"user-balance-payment-topup-reversal:{payment_id}"
        existing = await user_balance_dal.get_ledger_entry_by_key(session, key)
        if existing is not None:
            if (
                int(existing.user_id) != int(credit.user_id)
                or str(existing.currency).upper() != str(credit.currency).upper()
                or int(existing.amount_minor) != -int(credit.amount_minor)
            ):
                raise UserBalanceError("user_balance_reversal_conflict", 409)
            return existing
        return await user_balance_dal.create_ledger_entry(
            session,
            user_id=int(credit.user_id),
            currency=str(credit.currency),
            currency_scale=int(credit.currency_scale),
            amount_minor=-int(credit.amount_minor),
            kind="payment_topup_reversal",
            state="posted",
            reference_type="payment",
            reference_id=str(payment_id),
            idempotency_key=key,
            reason=reason,
            posted_at=datetime.now(UTC),
        )

    async def admin_adjust(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        actor_admin_id: int,
        target: Literal["user", "partner"] = "user",
        mode: Literal["add", "subtract", "set"],
        amount: Any,
        reason: str,
        idempotency_key: str,
    ) -> UserBalanceLedgerEntry | PartnerLedgerEntry:
        if target == "partner":
            if not self.settings.partner_settings.enabled:
                raise UserBalanceError("partner_program_disabled", 409)
            profile = await partner_dal.get_profile_by_user_id(session, user_id, for_update=True)
            if profile is None:
                raise UserBalanceError("partner_not_found", 404)
            requested_minor = amount_to_minor(amount, scale=self.scale)
            if requested_minor < 0:
                raise UserBalanceError("invalid_balance_amount", 400)
            try:
                entry, _ = await PartnerCommissionService(self.settings).adjust_balance(
                    session,
                    partner_id=int(profile.partner_id),
                    currency=self.currency,
                    scale=self.scale,
                    mode=mode,
                    amount_minor=requested_minor,
                    reason=reason,
                    actor_admin_id=actor_admin_id,
                    idempotency_key=idempotency_key,
                )
            except PartnerError as exc:
                raise UserBalanceError(exc.code, exc.status, exc.message) from exc
            return entry
        user = await user_dal.lock_user_by_id(session, user_id)
        if user is None:
            raise UserBalanceError("user_not_found", 404)
        existing = await user_balance_dal.get_ledger_entry_by_key(session, idempotency_key)
        if existing is not None:
            if (
                int(existing.user_id) != user_id
                or str(existing.currency).upper() != self.currency
                or str(existing.kind) != "admin_adjustment"
            ):
                raise UserBalanceError("user_balance_adjustment_conflict", 409)
            return existing
        requested_minor = amount_to_minor(amount, scale=self.scale)
        if requested_minor < 0:
            raise UserBalanceError("invalid_balance_amount", 400)
        current = await user_balance_dal.balance_minor(session, user_id, self.currency)
        delta = requested_minor - current if mode == "set" else requested_minor
        if mode == "subtract":
            delta = -requested_minor
        if current + delta < 0:
            raise UserBalanceError("insufficient_user_balance", 409)
        return await user_balance_dal.create_ledger_entry(
            session,
            user_id=user_id,
            currency=self.currency,
            currency_scale=self.scale,
            amount_minor=delta,
            kind="admin_adjustment",
            state="posted",
            reference_type="admin",
            reference_id=str(actor_admin_id),
            idempotency_key=idempotency_key,
            actor_admin_id=actor_admin_id,
            reason=reason.strip() or "Admin balance adjustment",
            posted_at=datetime.now(UTC),
        )

    async def convert(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        actor_admin_id: int,
        direction: Literal["partner_to_user", "user_to_partner"],
        amount: Any,
        reason: str,
        idempotency_key: str,
    ) -> tuple[UserBalanceLedgerEntry, PartnerLedgerEntry]:
        amount_minor = amount_to_minor(amount, scale=self.scale)
        if amount_minor <= 0:
            raise UserBalanceError("invalid_balance_amount", 400)
        if not self.settings.partner_settings.enabled:
            raise UserBalanceError("partner_program_disabled", 409)
        user = await user_dal.lock_user_by_id(session, user_id)
        if user is None:
            raise UserBalanceError("user_not_found", 404)
        profile = await partner_dal.get_profile_by_user_id(session, user_id, for_update=True)
        if profile is None:
            raise UserBalanceError("partner_not_found", 404)
        if str(profile.status) != "active":
            raise UserBalanceError("partner_not_active", 409)
        user_amount = amount_minor if direction == "partner_to_user" else -amount_minor
        partner_amount = -amount_minor if direction == "partner_to_user" else amount_minor
        user_key = f"{idempotency_key}:user"
        partner_key = f"{idempotency_key}:partner"
        existing_user = await user_balance_dal.get_ledger_entry_by_key(session, user_key)
        existing_partner = await partner_dal.get_ledger_entry_by_key(session, partner_key)
        if existing_user is not None and existing_partner is not None:
            if (
                int(existing_user.user_id) != user_id
                or str(existing_user.currency).upper() != self.currency
                or int(existing_user.amount_minor) != user_amount
                or int(existing_partner.partner_id) != int(profile.partner_id)
                or str(existing_partner.currency).upper() != self.currency
                or int(existing_partner.amount_minor) != partner_amount
            ):
                raise UserBalanceError("balance_conversion_conflict", 409)
            return existing_user, existing_partner
        if existing_user is not None or existing_partner is not None:
            raise UserBalanceError("balance_conversion_conflict", 409)
        partner_withdrawable_delta = 0
        if user_amount < 0:
            available = await user_balance_dal.balance_minor(session, user_id, self.currency)
            if available < amount_minor:
                raise UserBalanceError("insufficient_user_balance", 409)
        else:
            available = await partner_dal.balance_minor(
                session,
                int(profile.partner_id),
                self.currency,
            )
            if available < amount_minor:
                raise UserBalanceError("insufficient_partner_balance", 409)
            withdrawable = await partner_dal.withdrawable_balance_minor(
                session,
                int(profile.partner_id),
                self.currency,
            )
            non_withdrawable = max(0, available - withdrawable)
            partner_withdrawable_delta = -max(0, amount_minor - non_withdrawable)
        user_entry = await user_balance_dal.create_ledger_entry(
            session,
            user_id=user_id,
            currency=self.currency,
            currency_scale=self.scale,
            amount_minor=user_amount,
            kind=("partner_conversion_in" if user_amount > 0 else "partner_conversion_out"),
            state="posted",
            reference_type="partner",
            reference_id=str(profile.partner_id),
            idempotency_key=user_key,
            actor_admin_id=actor_admin_id,
            reason=reason.strip() or "Balance conversion",
            posted_at=datetime.now(UTC),
        )
        partner_entry = await partner_dal.create_ledger_entry(
            session,
            partner_id=int(profile.partner_id),
            currency=self.currency,
            currency_scale=self.scale,
            amount_minor=partner_amount,
            withdrawable_amount_minor=partner_withdrawable_delta,
            kind=("balance_conversion_in" if partner_amount > 0 else "balance_conversion_out"),
            state="posted",
            reference_type="user_balance",
            reference_id=str(user_entry.entry_id),
            idempotency_key=partner_key,
            actor_admin_id=actor_admin_id,
            reason=reason.strip() or "Balance conversion",
            posted_at=datetime.now(UTC),
        )
        return user_entry, partner_entry
