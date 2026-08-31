# SQLAlchemy legacy Column declarations expose instance attributes as Column[T]
# to mypy; this service intentionally mutates loaded ORM instances.
# mypy: disable-error-code="assignment,arg-type"

from __future__ import annotations

import base64
import json
import os
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra import events
from bot.infra.event_payloads import (
    PartnerWithdrawalRequestedPayload,
    PartnerWithdrawalStatusChangedPayload,
)
from bot.services.partner_common import PartnerError, as_utc, compact_json
from config.settings import Settings
from config.settings_models import PartnerWithdrawalMethod
from db.dal import partner_dal
from db.partner_models import PartnerWithdrawal

_CARD_DIGITS = re.compile(r"^\d{12,19}$")
_PHONE_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def _valid_crypto_address(value: str) -> bool:
    """Accept address formats from different chains without accepting hidden text."""

    return 4 <= len(value) <= 256 and all(
        not character.isspace() and not unicodedata.category(character).startswith("C")
        for character in value
    )


def _luhn_valid(value: str) -> bool:
    total = 0
    parity = len(value) % 2
    for index, character in enumerate(value):
        digit = int(character)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def normalize_partner_encryption_key(raw: str) -> bytes:
    value = raw.strip()
    try:
        padded = value + "=" * (-len(value) % 4)
        key = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise PartnerError("partner_encryption_key_invalid", 503) from exc
    if len(key) not in {16, 24, 32}:
        raise PartnerError("partner_encryption_key_invalid", 503)
    return key


def encrypt_partner_requisites(
    payload: dict[str, str],
    *,
    raw_key: str,
    associated_data: bytes,
) -> bytes:
    nonce = os.urandom(12)
    plaintext = compact_json(payload).encode("utf-8")
    aes = AESGCM(normalize_partner_encryption_key(raw_key))
    return nonce + aes.encrypt(nonce, plaintext, associated_data)


def decrypt_partner_requisites(
    ciphertext: bytes,
    *,
    raw_key: str,
    associated_data: bytes,
) -> dict[str, str]:
    if len(ciphertext) < 29:
        raise PartnerError("withdrawal_requisites_unavailable", 409)
    nonce, encrypted = ciphertext[:12], ciphertext[12:]
    try:
        aes = AESGCM(normalize_partner_encryption_key(raw_key))
        payload = json.loads(aes.decrypt(nonce, encrypted, associated_data))
    except PartnerError:
        raise
    except Exception as exc:
        raise PartnerError("withdrawal_requisites_unavailable", 409) from exc
    if not isinstance(payload, dict):
        raise PartnerError("withdrawal_requisites_unavailable", 409)
    return {str(key): str(value) for key, value in payload.items()}


class PartnerWithdrawalService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def config(self):
        return self.settings.partner_settings

    def encryption_available(self) -> bool:
        secret = self.settings.PARTNER_REQUISITES_ENCRYPTION_KEY
        if not secret:
            return False
        try:
            normalize_partner_encryption_key(secret.get_secret_value())
        except PartnerError:
            return False
        return True

    def _aes(self) -> AESGCM:
        secret = self.settings.PARTNER_REQUISITES_ENCRYPTION_KEY
        if not secret:
            raise PartnerError("partner_encryption_key_missing", 503)
        return AESGCM(normalize_partner_encryption_key(secret.get_secret_value()))

    def _encrypt(self, payload: dict[str, str], *, associated_data: bytes) -> bytes:
        secret = self.settings.PARTNER_REQUISITES_ENCRYPTION_KEY
        if not secret:
            raise PartnerError("partner_encryption_key_missing", 503)
        return encrypt_partner_requisites(
            payload,
            raw_key=secret.get_secret_value(),
            associated_data=associated_data,
        )

    def _decrypt(self, ciphertext: bytes, *, associated_data: bytes) -> dict[str, str]:
        secret = self.settings.PARTNER_REQUISITES_ENCRYPTION_KEY
        if not secret:
            raise PartnerError("partner_encryption_key_missing", 503)
        return decrypt_partner_requisites(
            ciphertext,
            raw_key=secret.get_secret_value(),
            associated_data=associated_data,
        )

    def method(self, method_id: str) -> PartnerWithdrawalMethod:
        normalized = method_id.strip().lower()
        for method in self.config.withdrawal_methods:
            if method.id == normalized:
                return method
        raise PartnerError("withdrawal_method_not_found", 404)

    def _validated_requisites(
        self,
        method: PartnerWithdrawalMethod,
        raw: dict[str, Any],
        network: str | None,
    ) -> tuple[dict[str, str], str]:
        requisites = {
            str(key): str(value).strip() for key, value in raw.items() if str(value).strip()
        }
        required = {field.id for field in method.fields if field.required}
        if method.type == "bank_card":
            required.add("card_number")
            number = re.sub(r"[\s-]+", "", requisites.get("card_number", ""))
            if not _CARD_DIGITS.fullmatch(number) or not _luhn_valid(number):
                raise PartnerError("invalid_card_number", 400)
            requisites["card_number"] = number
            mask = f"•••• {number[-4:]}"
        elif method.type == "sbp":
            required.add("phone")
            phone = re.sub(r"[\s()\-]+", "", requisites.get("phone", ""))
            if phone.startswith("8") and len(phone) == 11:
                phone = f"+7{phone[1:]}"
            if not _PHONE_E164.fullmatch(phone):
                raise PartnerError("invalid_phone", 400)
            requisites["phone"] = phone
            mask = f"{phone[:3]}••••{phone[-4:]}"
        else:
            required.add("address")
            address = requisites.get("address", "")
            if not _valid_crypto_address(address):
                raise PartnerError("invalid_crypto_address", 400)
            allowed_networks = {item.id for item in method.networks}
            normalized_network = str(network or requisites.get("network") or "").strip().lower()
            if normalized_network not in allowed_networks:
                raise PartnerError("invalid_crypto_network", 400)
            requisites["network"] = normalized_network
            selected_network = next(
                item for item in method.networks if item.id == normalized_network
            )
            network_label = selected_network.label.strip() or selected_network.id
            mask = f"{network_label} · ••••{address[-8:]}"
        missing = sorted(key for key in required if not requisites.get(key))
        if missing:
            raise PartnerError("withdrawal_requisites_incomplete", 400, ", ".join(missing))
        allowed = {field.id for field in method.fields} | required | {"network"}
        sanitized = {key: value for key, value in requisites.items() if key in allowed}
        return sanitized, mask[:255]

    async def create_request(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        method_id: str,
        amount_minor: int,
        currency: str,
        requisites: dict[str, Any],
        network: str | None,
        idempotency_key: str,
    ) -> PartnerWithdrawal:
        existing = await partner_dal.get_withdrawal_by_idempotency_key(session, idempotency_key)
        if existing:
            profile = await partner_dal.get_profile_by_user_id(session, user_id)
            if profile and int(existing.partner_id) == int(profile.partner_id):
                normalized_currency = currency.strip().upper()
                normalized_network = (
                    str(network or requisites.get("network") or "").strip().lower() or None
                )
                if (
                    str(existing.method_id_snapshot) != method_id.strip().lower()
                    or int(existing.debit_amount_minor) != amount_minor
                    or str(existing.debit_currency).upper() != normalized_currency
                    or (str(existing.network).lower() if existing.network else None)
                    != normalized_network
                ):
                    raise PartnerError("idempotency_key_conflict", 409)
                if existing.requisites_ciphertext and self.encryption_available():
                    try:
                        snapshot = PartnerWithdrawalMethod.model_validate_json(
                            str(existing.method_snapshot_json)
                        )
                        normalized_requisites, _ = self._validated_requisites(
                            snapshot,
                            requisites,
                            network,
                        )
                        associated_data = (
                            f"partner:{int(profile.partner_id)}:{idempotency_key}".encode()
                        )
                        stored_requisites = self._decrypt(
                            bytes(existing.requisites_ciphertext),
                            associated_data=associated_data,
                        )
                        if stored_requisites != normalized_requisites:
                            raise PartnerError("idempotency_key_conflict", 409)
                    except PartnerError:
                        raise
                    except Exception as exc:
                        raise PartnerError("idempotency_key_conflict", 409) from exc
                return existing
            raise PartnerError("idempotency_key_conflict", 409)
        if not self.config.enabled:
            raise PartnerError("partner_program_disabled", 403)
        if not self.config.withdrawals_enabled:
            raise PartnerError("partner_withdrawals_disabled", 403)
        profile = await partner_dal.get_profile_by_user_id(session, user_id, for_update=True)
        if not profile:
            raise PartnerError("partner_not_found", 404)
        if profile.status != "active":
            raise PartnerError("partner_not_active", 403)
        latest = await partner_dal.latest_withdrawal_for_partner(
            session,
            int(profile.partner_id),
        )
        if latest and as_utc(latest.requested_at) + timedelta(
            seconds=self.config.withdrawal_rate_limit_seconds
        ) > datetime.now(UTC):
            raise PartnerError("withdrawal_rate_limited", 429)
        method = self.method(method_id)
        if not method.enabled:
            raise PartnerError("withdrawal_method_disabled", 403)
        normalized_currency = currency.strip().upper()
        if normalized_currency != method.debit_currency:
            raise PartnerError("withdrawal_currency_mismatch", 400)
        if amount_minor < method.min_amount_minor:
            raise PartnerError("withdrawal_below_minimum", 400)
        if method.max_amount_minor is not None and amount_minor > method.max_amount_minor:
            raise PartnerError("withdrawal_above_maximum", 400)
        if (
            await partner_dal.active_withdrawal_count(session, int(profile.partner_id))
            >= self.config.max_active_withdrawals
        ):
            raise PartnerError("too_many_active_withdrawals", 429)
        available = await partner_dal.withdrawable_balance_minor(
            session,
            int(profile.partner_id),
            normalized_currency,
        )
        if available < amount_minor or amount_minor <= 0:
            raise PartnerError("insufficient_partner_balance", 409)
        normalized_requisites, mask = self._validated_requisites(method, requisites, network)
        now = datetime.now(UTC)
        associated_data = f"partner:{int(profile.partner_id)}:{idempotency_key}".encode()
        ciphertext = self._encrypt(normalized_requisites, associated_data=associated_data)
        method_snapshot = method.model_dump(mode="json")
        withdrawal = await partner_dal.create_withdrawal(
            session,
            partner_id=int(profile.partner_id),
            method_id_snapshot=method.id,
            method_type_snapshot=method.type,
            method_snapshot_json=compact_json(method_snapshot),
            debit_amount_minor=amount_minor,
            debit_currency=normalized_currency,
            currency_scale=method.currency_scale,
            settlement_asset=method.settlement_asset,
            network=normalized_requisites.get("network"),
            status="requested",
            status_version=1,
            requisites_ciphertext=ciphertext,
            requisites_key_id=str(self.settings.PARTNER_REQUISITES_KEY_ID),
            masked_requisites=mask,
            client_idempotency_key=idempotency_key,
            requested_at=now,
        )
        await partner_dal.create_ledger_entry(
            session,
            partner_id=int(profile.partner_id),
            currency=normalized_currency,
            currency_scale=method.currency_scale,
            amount_minor=-amount_minor,
            kind="withdrawal_reserve",
            state="posted",
            reference_type="withdrawal",
            reference_id=str(withdrawal.withdrawal_id),
            idempotency_key=f"withdrawal-reserve:{int(withdrawal.withdrawal_id)}",
            posted_at=now,
        )
        await partner_dal.create_audit_event(
            session,
            event_type="withdrawal_requested",
            actor_type="user",
            partner_id=int(profile.partner_id),
            withdrawal_id=int(withdrawal.withdrawal_id),
            actor_user_id=user_id,
            new_values_json=compact_json(
                {
                    "status": "requested",
                    "currency": normalized_currency,
                    "amount_minor": amount_minor,
                    "method_id": method.id,
                }
            ),
        )
        await events.emit_model(
            PartnerWithdrawalRequestedPayload(
                partner_id=int(profile.partner_id),
                user_id=user_id,
                withdrawal_id=int(withdrawal.withdrawal_id),
                status="requested",
                currency=normalized_currency,
                currency_scale=int(withdrawal.currency_scale),
                amount_minor=amount_minor,
                requested_at=now,
            )
        )
        return withdrawal

    async def _release_reserve(
        self,
        session: AsyncSession,
        withdrawal: PartnerWithdrawal,
        *,
        reason: str,
    ) -> None:
        key = f"withdrawal-release:{int(withdrawal.withdrawal_id)}"
        if await partner_dal.get_ledger_entry_by_key(session, key):
            return
        await partner_dal.create_ledger_entry(
            session,
            partner_id=int(withdrawal.partner_id),
            currency=str(withdrawal.debit_currency),
            currency_scale=int(withdrawal.currency_scale),
            amount_minor=int(withdrawal.debit_amount_minor),
            kind="withdrawal_release",
            state="posted",
            reference_type="withdrawal",
            reference_id=str(withdrawal.withdrawal_id),
            idempotency_key=key,
            reason=reason,
            posted_at=datetime.now(UTC),
        )

    async def cancel_request(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        withdrawal_id: int,
    ) -> PartnerWithdrawal:
        profile = await partner_dal.get_profile_by_user_id(session, user_id, for_update=True)
        withdrawal = await partner_dal.get_withdrawal_by_id(
            session,
            withdrawal_id,
            for_update=True,
        )
        if not profile or not withdrawal or int(withdrawal.partner_id) != int(profile.partner_id):
            raise PartnerError("withdrawal_not_found", 404)
        if withdrawal.status == "canceled":
            return withdrawal
        if withdrawal.status != "requested":
            raise PartnerError("withdrawal_cannot_be_canceled", 409)
        await self._transition(
            session,
            withdrawal,
            status="canceled",
            actor_type="user",
            actor_user_id=user_id,
            message=None,
            release=True,
        )
        return withdrawal

    async def admin_transition(
        self,
        session: AsyncSession,
        *,
        withdrawal_id: int,
        status: str,
        expected_version: int,
        actor_admin_id: int,
        message: str | None = None,
        external_reference: str | None = None,
        settlement_amount: str | None = None,
    ) -> PartnerWithdrawal:
        withdrawal = await partner_dal.get_withdrawal_by_id(
            session,
            withdrawal_id,
            for_update=True,
        )
        if not withdrawal:
            raise PartnerError("withdrawal_not_found", 404)
        if not withdrawal.requisites_ciphertext:
            raise PartnerError("withdrawal_requisites_unavailable", 409)
        if int(withdrawal.status_version) != expected_version:
            raise PartnerError("stale_withdrawal", 409)
        normalized = status.strip().lower()
        transitions = {
            "requested": {"processing", "rejected", "failed"},
            "processing": {"paid", "rejected", "failed"},
            "failed": {"processing", "rejected"},
        }
        if normalized == withdrawal.status:
            return withdrawal
        if normalized not in transitions.get(str(withdrawal.status), set()):
            raise PartnerError("invalid_withdrawal_transition", 409)
        if normalized == "rejected" and not str(message or "").strip():
            raise PartnerError("withdrawal_rejection_reason_required", 400)
        if (
            normalized == "paid"
            and withdrawal.method_type_snapshot == "crypto"
            and not str(settlement_amount or "").strip()
        ):
            raise PartnerError("settlement_amount_required", 400)
        withdrawal.external_reference = str(external_reference or "").strip() or None
        withdrawal.settlement_amount = str(settlement_amount or "").strip() or None
        await self._transition(
            session,
            withdrawal,
            status=normalized,
            actor_type="admin",
            actor_user_id=actor_admin_id,
            message=message,
            release=normalized == "rejected",
        )
        return withdrawal

    async def _transition(
        self,
        session: AsyncSession,
        withdrawal: PartnerWithdrawal,
        *,
        status: str,
        actor_type: str,
        actor_user_id: int,
        message: str | None,
        release: bool,
    ) -> None:
        old = str(withdrawal.status)
        now = datetime.now(UTC)
        withdrawal.status = status
        withdrawal.status_version = int(withdrawal.status_version) + 1
        withdrawal.status_message = str(message or "").strip() or None
        if actor_type == "admin":
            withdrawal.handled_by_admin_id = actor_user_id
        if status == "processing":
            withdrawal.processing_at = now
        if status == "paid":
            withdrawal.paid_at = now
            withdrawal.decided_at = now
        if status in {"rejected", "canceled", "failed"}:
            withdrawal.decided_at = now
        if release:
            await self._release_reserve(session, withdrawal, reason=f"withdrawal {status}")
        await session.flush()
        await partner_dal.create_audit_event(
            session,
            event_type="withdrawal_status_changed",
            actor_type=actor_type,
            partner_id=int(withdrawal.partner_id),
            withdrawal_id=int(withdrawal.withdrawal_id),
            actor_user_id=actor_user_id,
            old_values_json=compact_json({"status": old}),
            new_values_json=compact_json(
                {"status": status, "status_version": int(withdrawal.status_version)}
            ),
            reason=withdrawal.status_message,
        )
        await events.emit_model(
            PartnerWithdrawalStatusChangedPayload(
                partner_id=int(withdrawal.partner_id),
                user_id=await self._partner_user_id(session, int(withdrawal.partner_id)),
                withdrawal_id=int(withdrawal.withdrawal_id),
                old_status=old,
                status=status,
                status_version=int(withdrawal.status_version),
                currency=str(withdrawal.debit_currency),
                currency_scale=int(withdrawal.currency_scale),
                amount_minor=int(withdrawal.debit_amount_minor),
                settlement_amount=(
                    str(withdrawal.settlement_amount) if withdrawal.settlement_amount else None
                ),
                external_reference=(
                    str(withdrawal.external_reference) if withdrawal.external_reference else None
                ),
                changed_at=now,
            )
        )

    @staticmethod
    async def _partner_user_id(session: AsyncSession, partner_id: int) -> int | None:
        profile = await partner_dal.get_profile_by_id(session, partner_id)
        return int(profile.user_id) if profile and profile.user_id is not None else None

    async def reveal_requisites(
        self,
        session: AsyncSession,
        *,
        withdrawal_id: int,
        actor_admin_id: int,
    ) -> dict[str, str]:
        withdrawal = await partner_dal.get_withdrawal_by_id(session, withdrawal_id)
        if not withdrawal:
            raise PartnerError("withdrawal_not_found", 404)
        associated_data = (
            f"partner:{int(withdrawal.partner_id)}:{withdrawal.client_idempotency_key}".encode()
        )
        payload = self._decrypt(
            bytes(withdrawal.requisites_ciphertext), associated_data=associated_data
        )
        await partner_dal.create_audit_event(
            session,
            event_type="withdrawal_requisites_revealed",
            actor_type="admin",
            partner_id=int(withdrawal.partner_id),
            withdrawal_id=withdrawal_id,
            actor_user_id=actor_admin_id,
        )
        return payload
