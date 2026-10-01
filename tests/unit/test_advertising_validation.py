"""Input boundaries and portable CSV behavior, independent of provider formats."""

import math
from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from bot.app.web.admin_api_impl.activity_schemas import AdCreateBody, AdToggleBody
from bot.services.advertising.imports import export_csv, normalize_csv
from bot.services.advertising.validation import landing_path, minor_units, start_code


@pytest.mark.parametrize(
    "value",
    [
        "ref_a",
        "p_code",
        "promo_code",
        "plan_basic",
        "gift_a",
        "admin_x",
        "ticket_a",
        "webapp_auth_x",
        "two words",
        "a" * 65,
        "\u043a\u043e\u0434",
    ],
)
def test_codes_reject_reserved_or_nonportable_payloads(value: str) -> None:
    with pytest.raises(ValueError):
        start_code(value)


@pytest.mark.parametrize("cost", [math.nan, math.inf, -1, 100000001])
def test_create_rejects_nonfinite_or_invalid_cost(cost: float) -> None:
    with pytest.raises(ValidationError):
        AdCreateBody(source="QA", start_param="qa_channel", cost=cost)


@pytest.mark.parametrize("value", ["false", "true", 0, 1])
def test_status_is_a_json_boolean(value: object) -> None:
    with pytest.raises(ValidationError):
        AdToggleBody.model_validate({"is_active": value})


def csv_rows(source: str, granularity: str = "daily") -> list[dict[str, Any]]:
    rows = normalize_csv(
        source,
        mapping={"start": "start", "end": "end", "advertisement": "ad", "cost": "cost"},
        timezone_name="Europe/Berlin",
        account="qa",
        granularity=granularity,
        currency="TON",
        delimiter=";",
    )

    return list(rows)


def test_bom_local_day_and_exact_currency_units() -> None:
    rows = csv_rows("\ufeffstart;end;ad;cost\n2026-03-29;;qa;0.123456789\n")
    assert rows[0]["cost_minor"] == 123456789
    assert (
        datetime.fromisoformat(rows[0]["interval_end"])
        - datetime.fromisoformat(rows[0]["interval_start"])
    ).total_seconds() == 23 * 3600
    assert minor_units("99999999.123456789", "TON") == 99999999123456789


@pytest.mark.parametrize(
    "source,granularity",
    [
        ("start;end;ad;cost\n2026-10-25T02:30:00;;qa;1\n", "daily"),
        ("start;end;ad;cost\n2026-03-29T02:30:00;;qa;1\n", "daily"),
        ("start;end;ad;cost\n2026-01-01;;qa;1\n2026-01-01;;qa;2\n", "daily"),
        ("start;end;ad;cost\n2026-01-01;2026-01-03;qa;1\n2026-01-02;2026-01-04;qa;2\n", "interval"),
        ("start;end;ad;cost\n2026-01-01;;qa;1\n", "cumulative"),
    ],
)
def test_ambiguous_or_overlapping_csv_is_rejected(source: str, granularity: str) -> None:
    with pytest.raises(ValueError):
        csv_rows(source, granularity)


def test_cumulative_total_is_one_interval_and_formula_export_is_escaped() -> None:
    rows = csv_rows("start;end;ad;cost\n2026-01-01;2026-02-01;qa;4\n", "cumulative")
    assert len(rows) == 1 and rows[0]["cost_minor"] == 4000000000
    csv = export_csv([{"a": "=1+1", "b": "  @command", "c": "-formula", "d": "+formula"}])
    assert "'=1+1" in csv and "'  @command" in csv and "'-formula" in csv and "'+formula" in csv


@pytest.mark.parametrize("path", ["https://other.test/", "//other.test", "/\\other", "../outside"])
def test_landing_is_a_local_absolute_path(path: str) -> None:
    with pytest.raises(ValueError):
        landing_path(path)


def test_feature_flag_disables_new_workspace_but_checks_admin_identity_first() -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock, patch

    from aiohttp import web

    from bot.app.web.admin_api_impl.advertising_access import require_advertising_admin

    with (
        patch(
            "bot.app.web.admin_api_impl.advertising_access._require_admin_user_id", return_value=1
        ) as auth,
        patch(
            "bot.app.web.admin_api_impl.advertising_access.get_settings",
            return_value=SimpleNamespace(ADVERTISING_ENABLED=False),
        ),
    ):
        request = Mock()
        with pytest.raises(web.HTTPNotFound, match="Not Found"):
            require_advertising_admin(request)
        auth.assert_called_once_with(request)


def test_missing_platform_columns_are_distinguished_from_measured_zero() -> None:
    rows = normalize_csv(
        "start,ad,views\n2026-09-01T00:00:00Z,qa,0\n",
        mapping={"start": "start", "advertisement": "ad", "impressions": "views"},
        timezone_name="UTC",
        account="qa",
        granularity="daily",
        currency=None,
        delimiter=",",
    )
    assert rows[0]["available_metrics"] == ["impressions"]
    assert rows[0]["impressions"] == 0 and rows[0]["clicks"] == 0
