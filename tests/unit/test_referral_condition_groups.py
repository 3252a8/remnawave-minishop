from types import SimpleNamespace
from typing import Any, cast

from bot.app.web.webapp.referral_serializers import _serialize_tariff_referral_bonus_details
from config.settings import Settings
from config.tariffs_config import Tariff, TariffsConfig


def tariff(key: str, **changes: object) -> Tariff:
    value: dict[str, object] = {
        "key": key,
        "names": {"en": key.title()},
        "squad_uuids": [key],
        "billing_model": "period",
        "monthly_gb": 100,
        "prices_rub": {"1": 100, "3": 300},
        "enabled_periods": [1, 3],
        "referral_bonus_days_inviter": {"1": 3, "3": 7},
        "referral_bonus_days_referee": {"1": 1, "3": 2},
    }
    value.update(changes)
    return Tariff.model_validate(value)


def summaries(*tariffs: Tariff) -> list[dict[str, Any]]:
    catalog = TariffsConfig.model_validate(
        {"default_tariff": tariffs[0].key, "tariffs": [item.model_dump() for item in tariffs]}
    )
    settings = cast(Settings, SimpleNamespace(tariffs_config=catalog))
    return cast(list[dict[str, Any]], _serialize_tariff_referral_bonus_details(settings, "en"))


def test_identical_conditions_group_and_preserve_all_tariff_names() -> None:
    result = summaries(tariff("standard"), tariff("premium"), tariff("other"))
    assert len(result) == 1
    assert result[0]["tariff_keys"] == ["standard", "premium", "other"]
    assert result[0]["tariff_names"] == ["Standard", "Premium", "Other"]
    assert [item["inviter_days"] for item in result[0]["details"]] == [3, 7]


def test_same_min_max_different_period_rewards_stay_separate() -> None:
    result = summaries(
        tariff("standard"),
        tariff("premium", referral_bonus_days_inviter={"1": 7, "3": 3}),
    )
    assert len(result) == 2


def test_disabled_access_controlled_tariff_is_not_advertised() -> None:
    result = summaries(
        tariff("standard"),
        tariff("other"),
        tariff("premium", enabled=False, access_code="a" * 32),
    )
    assert result[0]["tariff_keys"] == ["standard", "other"]


def test_different_durations_stay_separate() -> None:
    assert (
        len(
            summaries(
                tariff("standard"),
                tariff("premium", period_unit="day"),
            )
        )
        == 2
    )


def test_additional_period_without_rewards_stays_separate() -> None:
    result = summaries(
        tariff("standard"),
        tariff("premium", enabled_periods=[1, 3, 6], prices_rub={"1": 100, "3": 300, "6": 600}),
    )
    assert len(result) == 2


def test_missing_and_explicit_zero_rewards_are_distinct() -> None:
    result = summaries(
        tariff("standard", referral_bonus_days_referee={}),
        tariff("premium", referral_bonus_days_referee={"1": 0, "3": 0}),
    )
    assert len(result) == 2


def test_no_rewards_return_no_summaries() -> None:
    assert (
        summaries(
            tariff("standard", referral_bonus_days_inviter={}, referral_bonus_days_referee={}),
            tariff("premium", referral_bonus_days_inviter={}, referral_bonus_days_referee={}),
        )
        == []
    )
