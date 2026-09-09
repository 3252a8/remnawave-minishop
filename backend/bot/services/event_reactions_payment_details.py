"""Localized payment failure details, including fixed-day subscriptions."""

import logging
from collections.abc import Callable
from typing import Any

from bot.infra.payment_events import PaymentPurchase, resolve_payment_success_snapshot
from bot.utils.subscription_periods import format_duration_days

logger = logging.getLogger(__name__)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_plain_amount(value: float) -> str:
    amount = float(value)
    if amount.is_integer():
        return str(int(amount))
    return f"{amount:g}"


def _tariff_display_name(settings: Any, tariff_key: str | None, language: str) -> str:
    if not tariff_key:
        return ""
    cfg = settings.tariffs_config
    if not cfg:
        return str(tariff_key)
    try:
        tariff = cfg.require(str(tariff_key))
        return str(tariff.name(language))
    except Exception:
        return str(tariff_key)


def _format_failed_payment_purchase(
    translate: Callable[..., str], purchase: PaymentPurchase
) -> str:
    if purchase.kind == "traffic":
        traffic_kind = translate(
            "payment_failed_traffic_kind_premium"
            if purchase.scope == "premium"
            else "payment_failed_traffic_kind_regular"
        )
        return translate(
            "payment_failed_detail_purchase_traffic",
            gb=_format_plain_amount(float(purchase.amount)),
            kind=traffic_kind,
        )
    if purchase.kind == "hwid_devices":
        return translate(
            "payment_failed_detail_purchase_hwid_devices",
            count=int(float(purchase.amount)),
        )
    label_kwargs = {
        "amount": _format_plain_amount(float(purchase.amount)),
        "unit": purchase.unit,
        "kind": purchase.kind,
        "scope": purchase.scope or "",
        **dict(purchase.label_kwargs),
    }
    if purchase.label_key:
        return translate(purchase.label_key, **label_kwargs)
    return translate("payment_failed_detail_purchase_generic", **label_kwargs)


def _failed_payment_provider_detail(
    settings: Any,
    payment: Any,
    payload: dict[str, Any],
    language: str,
) -> str:
    provider = str(
        payload.get("provider")
        or getattr(payment, "provider", None)
        or payload.get("notification_provider")
        or ""
    ).strip()
    if not provider:
        return ""
    try:
        from bot.payment_providers import (
            iter_provider_specs,
            provider_label_map,
            resolve_provider_presentation,
        )

        specs = tuple(iter_provider_specs())
        exact_spec = next((spec for spec in specs if provider == spec.id), None)
        provider_specs = [spec for spec in specs if provider == spec.provider_key]
        provider_label = provider_label_map(settings, language=language).get(provider, provider)
        if exact_spec is not None:
            button_label = resolve_provider_presentation(
                exact_spec,
                settings,
                language=language,
            ).webapp_label
            return f"{button_label} ({provider_label}; {provider})"
        if len(provider_specs) == 1:
            button_label = resolve_provider_presentation(
                provider_specs[0],
                settings,
                language=language,
            ).webapp_label
            return f"{button_label} ({provider_label}; {provider})"
        return f"{provider_label} ({provider})"
    except Exception:
        logger.exception("Failed to resolve payment provider label for %s.", provider)
        return provider


def _format_failed_payment_details(
    *,
    translate: Callable[..., str],
    settings: Any,
    language: str,
    payment: Any,
    payload: dict[str, Any],
) -> str:
    snapshot = resolve_payment_success_snapshot(
        payload,
        payment,
        default_currency=getattr(settings, "DEFAULT_CURRENCY", "RUB"),
    )
    lines: list[str] = []

    tariff_name = _tariff_display_name(settings, snapshot.tariff_key, language)
    if snapshot.duration_days:
        period = format_duration_days(snapshot.duration_days, translate, language)
        key = (
            "payment_failed_detail_period_with_tariff"
            if tariff_name
            else "payment_failed_detail_period"
        )
        lines.append(translate(key, period=period, tariff=tariff_name))
    elif snapshot.months > 0:
        key = (
            "payment_failed_detail_subscription_with_tariff"
            if tariff_name
            else "payment_failed_detail_subscription"
        )
        lines.append(translate(key, months=snapshot.months, tariff=tariff_name))

    for purchase in snapshot.purchases:
        detail = _format_failed_payment_purchase(translate, purchase)
        if detail:
            lines.append(detail)

    if not lines:
        description = str(getattr(payment, "description", "") or "").strip()
        if description:
            lines.append(description)

    details = [translate("payment_failed_detail_item", item=line) for line in lines if line]
    details.append(
        translate(
            "payment_failed_detail_amount",
            amount=_format_plain_amount(snapshot.amount),
            currency=snapshot.currency,
        )
    )
    provider_detail = _failed_payment_provider_detail(settings, payment, payload, language)
    if provider_detail:
        details.append(translate("payment_failed_detail_provider", provider=provider_detail))
    payment_id = getattr(payment, "payment_id", None)
    if payment_id is not None:
        details.append(translate("payment_failed_detail_payment_id", payment_id=payment_id))
    return "\n".join(details)
