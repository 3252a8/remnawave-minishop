"""Localized messages for successfully fulfilled payments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .common import Translator, format_human_units, sale_mode_base

_TRAFFIC_MODES = {"traffic", "traffic_package", "topup", "premium_topup"}
_HWID_DEVICE_MODES = {"hwid_device", "hwid_devices", "hwid_devices_renewal"}


def is_traffic_sale_base(sale_base: str) -> bool:
    return sale_base in _TRAFFIC_MODES


@dataclass
class SuccessMessage:
    """Inputs for ``build_success_message``."""

    translator: Translator
    sale_mode: str
    months: Any
    base_end_date: datetime | None
    final_end_date: datetime | None
    applied_referee_bonus_days: int = 0
    applied_promo_bonus_days: int = 0
    inviter_name: str | None = None
    referee_bonus_source: str = "referral"
    fallback_date_text: str = ""
    duration_days: int | None = None


def _fmt_date(dt: datetime | None, fallback: str) -> str:
    return dt.strftime("%Y-%m-%d") if dt else fallback


def build_success_message(payload: SuccessMessage) -> str:
    """Render the post-payment user-facing text.

    Picks one of: ``payment_successful_traffic_full`` /
    ``payment_successful_with_referral_bonus_full`` /
    ``payment_successful_with_promo_full`` / ``payment_successful_full``.
    """
    base = sale_mode_base(payload.sale_mode)
    _ = payload.translator
    end_text = _fmt_date(payload.final_end_date, payload.fallback_date_text)

    if base == "tariff_upgrade":
        return _("payment_successful_tariff_upgrade_full", end_date=end_text)

    if is_traffic_sale_base(base):
        return _(
            "payment_successful_traffic_full",
            traffic_gb=format_human_units(payload.months),
            end_date=end_text,
        )
    if base in _HWID_DEVICE_MODES:
        return _(
            "payment_successful_hwid_devices_full",
            count=format_human_units(payload.months),
        )
    if base == "trial":
        return _(
            "payment_successful_trial_full",
            days=format_human_units(payload.months),
            end_date=end_text,
        )
    if payload.duration_days is not None:
        text = _("payment_successful_days_full", days=payload.duration_days, end_date=end_text)
        if payload.applied_referee_bonus_days:
            text += "\n" + _(
                "payment_successful_bonus_days", days=payload.applied_referee_bonus_days
            )
        if payload.applied_promo_bonus_days:
            text += "\n" + _("payment_successful_bonus_days", days=payload.applied_promo_bonus_days)
        return text
    if payload.applied_referee_bonus_days and payload.final_end_date:
        base_end_text = _fmt_date(payload.base_end_date or payload.final_end_date, end_text)
        if payload.referee_bonus_source == "partner":
            return _(
                "payment_successful_with_partner_client_bonus_full",
                months=payload.months,
                base_end_date=base_end_text,
                bonus_days=payload.applied_referee_bonus_days,
                final_end_date=end_text,
            )
        return _(
            "payment_successful_with_referral_bonus_full",
            months=payload.months,
            base_end_date=base_end_text,
            bonus_days=payload.applied_referee_bonus_days,
            final_end_date=end_text,
            inviter_name=payload.inviter_name or _("friend_placeholder"),
        )
    if payload.applied_promo_bonus_days and payload.final_end_date:
        return _(
            "payment_successful_with_promo_full",
            months=payload.months,
            bonus_days=payload.applied_promo_bonus_days,
            end_date=end_text,
        )
    return _(
        "payment_successful_full",
        months=payload.months,
        end_date=end_text,
    )


def append_hwid_renewal_note(
    text: str,
    translator: Translator,
    *,
    count: Any,
    valid_until: datetime | None,
) -> str:
    try:
        count_int = int(count or 0)
    except (TypeError, ValueError):
        count_int = 0
    if count_int <= 0:
        return text
    date_text = valid_until.strftime("%Y-%m-%d") if valid_until else ""
    note = translator(
        "payment_successful_hwid_devices_renewal_note",
        count=format_human_units(count_int),
        date=date_text,
    )
    return f"{text}\n\n{note}"


def append_hwid_renewed_note(
    text: str,
    translator: Translator,
    *,
    count: Any,
    valid_until: datetime | None,
) -> str:
    try:
        count_int = int(count or 0)
    except (TypeError, ValueError):
        count_int = 0
    if count_int <= 0:
        return text
    date_text = valid_until.strftime("%Y-%m-%d") if valid_until else ""
    note = translator(
        "payment_successful_hwid_devices_renewed_note",
        count=format_human_units(count_int),
        date=date_text,
    )
    return f"{text}\n\n{note}"
