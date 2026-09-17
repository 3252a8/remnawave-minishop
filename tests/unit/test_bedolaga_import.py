from __future__ import annotations

import asyncio
from typing import Any

import pytest
from scripts.import_legacy import (
    DryRunSession,
    bedolaga_build_tariff_catalog,
    bedolaga_ledger_effect,
    bedolaga_target_user_id,
    build_arg_parser,
    ensure_distinct_databases,
)
from scripts.legacy_import.bedolaga_operations import _normalize_panel_api_url
from scripts.legacy_import.remnashop_base import _RemnashopImporterBase
from sqlalchemy import insert, select

from db.models import User


class _Result:
    def scalar_one_or_none(self) -> int:
        return 42


class _Session:
    def __init__(self) -> None:
        self.executed: list[Any] = []
        self.added: list[Any] = []

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        del args, kwargs
        self.executed.append(statement)
        return _Result()

    def add(self, instance: Any) -> None:
        self.added.append(instance)


class _BatchResult:
    def __init__(self, rows: list[dict[str, int]]) -> None:
        self.rows = rows

    def mappings(self) -> _BatchResult:
        return self

    def all(self) -> list[dict[str, int]]:
        return self.rows


class _BatchSource:
    def __init__(self) -> None:
        self.offsets: list[int] = []

    async def execute(self, statement: Any) -> _BatchResult:
        parameters = statement.compile().params
        offset = parameters["offset"]
        self.offsets.append(offset)
        rows = [{"id": item} for item in range(1, 6)]
        return _BatchResult(rows[offset : offset + parameters["batch_size"]])


def test_cli_registers_bedolaga_and_report_outputs() -> None:
    args = build_arg_parser().parse_args(
        [
            "--source-type",
            "bedolaga",
            "--source-dsn",
            "postgresql://old@source/bedolaga",
            "--inventory-output",
            "inventory.json",
            "--config-plan-output",
            "config.json",
            "--reconciliation-output",
            "reconciliation.json",
            "--summary-output",
            "summary.json",
        ]
    )

    assert args.source_type == "bedolaga"
    assert args.batch_size == 500
    assert args.inventory_output == "inventory.json"
    assert args.config_plan_output == "config.json"
    assert args.reconciliation_output == "reconciliation.json"
    assert args.summary_output == "summary.json"


def test_source_and_target_database_must_be_distinct() -> None:
    with pytest.raises(ValueError, match="same PostgreSQL database"):
        ensure_distinct_databases(
            "postgresql+asyncpg://source:one@localhost:5432/shop",
            "postgresql://target:two@127.0.0.1/shop",
        )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("https://panel.example.com", "https://panel.example.com/api"),
        ("https://panel.example.com/", "https://panel.example.com/api"),
        ("https://panel.example.com/api", "https://panel.example.com/api"),
        ("https://panel.example.com/api/", "https://panel.example.com/api"),
        ("", None),
    ],
)
def test_bedolaga_panel_api_url_is_normalized(source: str, expected: str | None) -> None:
    assert _normalize_panel_api_url(source) == expected


def test_dry_run_session_forwards_reads_and_suppresses_writes() -> None:
    async def exercise() -> tuple[_Result, _Session, DryRunSession, User | None]:
        session = _Session()
        dry_run = DryRunSession(session)

        result = await dry_run.execute(select(User.user_id))
        await dry_run.execute(insert(User).values(user_id=100))
        pending = User(user_id=200)
        dry_run.add(pending)
        loaded = await dry_run.get(User, 200)
        await dry_run.refresh(pending)
        return result, session, dry_run, loaded

    result, session, dry_run, loaded = asyncio.run(exercise())

    assert result.scalar_one_or_none() == 42
    assert len(session.executed) == 1
    assert session.added == []
    assert dry_run.suppressed_writes == 2
    assert loaded is not None and loaded.user_id == 200


def test_bedolaga_reader_uses_configured_stable_batches() -> None:
    async def exercise() -> tuple[list[dict[str, int]], list[int]]:
        importer: Any = object.__new__(_RemnashopImporterBase)
        importer.tables = {"users"}
        importer.source_schema = "public"
        importer.batch_size = 2
        importer.source = _BatchSource()
        rows = [row async for row in importer._iter_rows("users", order_by="id")]
        return rows, importer.source.offsets

    rows, offsets = asyncio.run(exercise())

    assert [row["id"] for row in rows] == [1, 2, 3, 4, 5]
    assert offsets == [0, 2, 4]


def test_bedolaga_email_only_ids_are_stable_and_outside_generated_range() -> None:
    assert bedolaga_target_user_id(17, None) == -9_000_000_000_000_017
    assert bedolaga_target_user_id(17, 123456) == 123456


def test_bedolaga_balance_effects_are_signed_minor_units() -> None:
    assert bedolaga_ledger_effect("deposit", 12500) == ("payment_topup", 12500)
    assert bedolaga_ledger_effect("subscription_payment", 9900) == (
        "checkout_spend",
        -9900,
    )
    assert bedolaga_ledger_effect("referral_reward", -700) == (
        "admin_adjustment",
        700,
    )
    assert bedolaga_ledger_effect("new", 0) is None


def test_bedolaga_tariff_catalog_preserves_days_prices_limits_and_status() -> None:
    result = bedolaga_build_tariff_catalog(
        [
            {
                "id": 2,
                "name": "PRO",
                "description": "Main tariff",
                "display_order": 1,
                "is_active": True,
                "traffic_limit_gb": 850,
                "device_limit": 6,
                "allowed_squads": ["11111111-1111-1111-1111-111111111111"],
                "period_prices": {"30": 29900, "90": 84900},
                "is_daily": False,
            },
            {
                "id": 3,
                "name": "Trial",
                "display_order": 2,
                "is_active": False,
                "traffic_limit_gb": 40,
                "device_limit": 1,
                "period_prices": {"7": 100},
                "is_daily": False,
            },
        ]
    )

    assert result["warnings"] == []
    assert result["tariff_map"]["2"] == "bedolaga-pro"
    catalog = result["catalog"]
    assert catalog["schema_version"] == 2
    assert catalog["period_unit"] == "day"
    assert catalog["default_tariff"] == "bedolaga-pro"
    assert catalog["tariffs"][0]["prices"]["rub"] == {"30": 299.0, "90": 849.0}
    assert catalog["tariffs"][0]["monthly_gb"] == 850.0
    assert catalog["tariffs"][0]["hwid_device_limit"] == 6
    assert catalog["tariffs"][1]["enabled"] is False
