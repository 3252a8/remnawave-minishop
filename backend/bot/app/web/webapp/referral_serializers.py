from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from config.settings import Settings
from config.subscription_periods import days_to_legacy_months, legacy_months_to_days

from .common import _format_days_title


def _legacy_referral_bonus_periods(settings: Settings) -> list[int]:
    if settings.traffic_sale_mode:
        return []
    return sorted(int(months) for months in settings.subscription_options)


def _serialize_tariff_period_referral_bonus_details(tariff: Any, lang: str) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for months in sorted(int(month) for month in tariff.enabled_periods):
        inviter_days = tariff.referral_inviter_bonus_days(months)
        friend_days = tariff.referral_referee_bonus_days(months)
        if inviter_days is None and friend_days is None:
            continue
        details.append(
            {
                "id": f"{tariff.key}:{months}",
                "tariff_key": tariff.key,
                "tariff_name": tariff.name(lang),
                "months": days_to_legacy_months(tariff.period_duration_days(int(months))),
                "duration_days": tariff.period_duration_days(int(months)),
                "title": _format_days_title(tariff.period_duration_days(int(months)), lang),
                "inviter_days": int(inviter_days or 0),
                "friend_days": int(friend_days or 0),
            }
        )
    return details


def _serialize_tariff_referral_bonus_details(settings: Settings, lang: str) -> list[dict[str, Any]]:
    tariffs_config = settings.tariffs_config
    if not tariffs_config:
        return []
    period_tariffs = [
        tariff for tariff in tariffs_config.enabled_tariffs if tariff.billing_model == "period"
    ]
    if len(period_tariffs) <= 1:
        return (
            _serialize_tariff_period_referral_bonus_details(period_tariffs[0], lang)
            if period_tariffs
            else []
        )

    summaries: list[dict[str, Any]] = []
    for tariff in period_tariffs:
        details = _serialize_tariff_period_referral_bonus_details(tariff, lang)
        if not details:
            continue
        inviter_values = [int(item["inviter_days"]) for item in details]
        friend_values = [int(item["friend_days"]) for item in details]
        summaries.append(
            {
                "id": f"tariff:{tariff.key}",
                "type": "tariff_summary",
                "tariff_key": tariff.key,
                "tariff_name": tariff.name(lang),
                "title": tariff.name(lang),
                "inviter_min_days": min(inviter_values),
                "inviter_max_days": max(inviter_values),
                "friend_min_days": min(friend_values),
                "friend_max_days": max(friend_values),
                "details": details,
            }
        )
    return summaries


def _serialize_referral_bonus_details(settings: Settings, lang: str) -> list[dict[str, Any]]:
    if settings.tariffs_config:
        return _serialize_tariff_referral_bonus_details(settings, lang)

    details: list[dict[str, Any]] = []
    for months in _legacy_referral_bonus_periods(settings):
        inviter_days = settings.referral_bonus_inviter.get(months)
        friend_days = settings.referral_bonus_referee.get(months)
        if inviter_days is None and friend_days is None:
            continue
        details.append(
            {
                "months": int(months),
                "title": _format_days_title(legacy_months_to_days(int(months)), lang),
                "inviter_days": int(inviter_days or 0),
                "friend_days": int(friend_days or 0),
            }
        )
    return details


def _build_webapp_referral_link(
    base_url: str | None,
    referral_code: str | None,
) -> str | None:
    if not base_url or not referral_code:
        return None
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["ref"] = f"u{referral_code}"
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path or "/",
            urlencode(query),
            parts.fragment,
        )
    )
