"""Characterize the import_legacy CLI surface and its mapping layer.

Safety net for packaging backend/scripts/import_legacy.py: the documented CLI
invocation (docs/migrations/remnashop.md, scripts/install.sh) and the
legacy_import_mappings / legacy_referral_codes write paths must keep working
unchanged through the split.
"""

import json
import subprocess
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest
from scripts.import_legacy import (
    RemnashopImporter,
    build_arg_parser,
    normalize_async_postgres_dsn,
    parse_only,
    parse_tariff_map,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert

from db.dal import user_dal

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCUMENTED_ENTRYPOINT = REPO_ROOT / "backend" / "scripts" / "import_legacy.py"


def test_documented_entrypoint_help_exits_zero_and_lists_every_flag():
    result = subprocess.run(
        [sys.executable, str(DOCUMENTED_ENTRYPOINT), "--help"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    for flag in (
        "--source-type",
        "--source-dsn",
        "--source-schema",
        "--source-env-file",
        "--source-crypt-key",
        "--target-dsn",
        "--only",
        "--on-conflict",
        "--dry-run",
        "--created-by-admin-id",
        "--tariff-map-json",
        "--no-admin-compat-overrides",
    ):
        assert flag in result.stdout


def test_arg_parser_defaults_match_documented_behavior():
    args = build_arg_parser().parse_args(["--source-dsn", "postgresql://s:s@h:5432/src"])

    assert args.source_type == "remnashop"
    assert args.source_schema == "public"
    assert args.source_env_file is None
    assert args.source_crypt_key is None
    assert args.target_dsn is None
    assert args.only == "all"
    assert args.on_conflict == "merge"
    assert args.dry_run is False
    assert args.created_by_admin_id == 0
    assert args.tariff_map_json is None
    assert args.no_admin_compat_overrides is False


def test_arg_parser_requires_source_dsn_and_validates_choices(capsys):
    parser = build_arg_parser()

    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args([])
    assert excinfo.value.code == 2

    with pytest.raises(SystemExit):
        parser.parse_args(["--source-dsn", "dsn", "--on-conflict", "explode"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--source-dsn", "dsn", "--source-type", "unknown-bot"])
    capsys.readouterr()


def test_parse_only_normalizes_sections():
    assert parse_only("") == set()
    assert parse_only("all") == {"all"}
    assert parse_only("Users, PAYMENTS ,,referrals") == {"users", "payments", "referrals"}


def test_parse_tariff_map_accepts_inline_json_and_file(tmp_path):
    assert parse_tariff_map(None) == {}
    assert parse_tariff_map('{"3": "pro"}') == {"3": "pro"}

    mapping_file = tmp_path / "tariff-map.json"
    mapping_file.write_text(json.dumps({"PRO": "pro"}), encoding="utf-8")
    assert parse_tariff_map(str(mapping_file)) == {"PRO": "pro"}

    with pytest.raises(ValueError):
        parse_tariff_map("[1, 2]")


def test_normalize_async_postgres_dsn_upgrades_sync_schemes():
    assert normalize_async_postgres_dsn("postgresql://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    assert normalize_async_postgres_dsn("postgres://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    assert (
        normalize_async_postgres_dsn("postgresql+asyncpg://u:p@h/db")
        == "postgresql+asyncpg://u:p@h/db"
    )


class _FakeSelectResult:
    """Empty-result stand-in for target-session SELECTs."""

    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return self

    def first(self):
        return None

    def all(self):
        return []


class _FakeSourceResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSourceConnection:
    """Synthetic legacy dump: serves SELECT * per table from canned rows."""

    def __init__(self, rows_by_table):
        self.rows_by_table = rows_by_table

    async def execute(self, clause):
        sql = str(clause)
        for table, rows in self.rows_by_table.items():
            if f'"{table}"' in sql:
                return _FakeSourceResult(rows)
        return _FakeSourceResult([])


class _FakeTargetSession:
    def __init__(self):
        self.executed: list[Any] = []
        self.added: list[Any] = []

    async def execute(self, statement):
        self.executed.append(statement)
        return _FakeSelectResult()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for index, obj in enumerate(self.added, start=1):
            if getattr(obj, "log_id", None) is None:
                obj.log_id = index

    def inserts(self, table_name):
        return [
            statement
            for statement in self.executed
            if isinstance(statement, Insert) and statement.table.name == table_name
        ]


def _insert_params(statement):
    return statement.compile(dialect=postgresql.dialect()).params


class ImportLegacyMappingLayerTests(unittest.IsolatedAsyncioTestCase):
    """Fixture-based mini-import over the legacy mapping tables."""

    def _importer(self, source, target, only):
        return RemnashopImporter(
            source=source,
            target=target,
            source_schema="public",
            only=only,
            on_conflict="merge",
            dry_run=True,
            created_by_admin_id=0,
            tariff_map={},
            write_admin_compat_overrides=False,
        )

    async def test_user_import_records_mappings_and_legacy_referral_codes(self):
        source = _FakeSourceConnection(
            {
                "users": [
                    {
                        "id": 1,
                        "telegram_id": 111,
                        "name": "Alice Legacy",
                        "username": "alice",
                        "language": "ru",
                        "referral_code": "LEGACY-ALICE",
                        "created_at": datetime(2025, 5, 1, tzinfo=UTC),
                        "is_blocked": False,
                        "is_bot_blocked": False,
                    },
                    {
                        "id": 2,
                        "telegram_id": 222,
                        "name": "Bob",
                        "username": "bob",
                        "language": "en",
                        "referral_code": None,
                        "created_at": datetime(2025, 6, 1, tzinfo=UTC),
                        "is_blocked": False,
                        "is_bot_blocked": False,
                    },
                ]
            }
        )
        target = _FakeTargetSession()
        importer = self._importer(source, target, only={"users"})
        importer.tables = {"users"}

        async def fake_create_user(session, user_data, *, registered_via="auto"):
            assert registered_via is None, "bulk import must not emit user.registered"
            return (
                SimpleNamespace(
                    user_id=user_data["user_id"],
                    referral_code=user_data.get("referral_code"),
                ),
                True,
            )

        with mock.patch.object(user_dal, "create_user", fake_create_user):
            await importer.import_users()

        self.assertEqual({111: 111, 222: 222}, importer.user_map)
        self.assertEqual(2, importer.summary["users"]["created"])

        referral_inserts = target.inserts("legacy_referral_codes")
        self.assertEqual(1, len(referral_inserts))
        referral_params = _insert_params(referral_inserts[0])
        self.assertEqual("remnashop", referral_params["source"])
        self.assertEqual("LEGACY-ALICE", referral_params["code"])
        self.assertEqual(111, referral_params["user_id"])
        self.assertIn(
            "ON CONFLICT (source, code) DO UPDATE",
            str(referral_inserts[0].compile(dialect=postgresql.dialect())),
        )

        mapping_inserts = target.inserts("legacy_import_mappings")
        by_entity: dict[str, list[dict[str, Any]]] = {}
        for statement in mapping_inserts:
            params = _insert_params(statement)
            self.assertEqual("remnashop", params["source"])
            by_entity.setdefault(params["entity_type"], []).append(params)

        self.assertEqual({"user", "user_state"}, set(by_entity))
        user_mappings = {params["source_id"]: params for params in by_entity["user"]}
        self.assertEqual({"111", "222"}, set(user_mappings))
        self.assertEqual("users", user_mappings["111"]["target_table"])
        self.assertEqual("111", user_mappings["111"]["target_id"])
        self.assertIn(
            "ON CONFLICT (source, entity_type, source_id) DO UPDATE",
            str(mapping_inserts[0].compile(dialect=postgresql.dialect())),
        )

        state_notes = by_entity["user_state"]
        self.assertEqual(2, len(state_notes))
        self.assertEqual(
            {"legacy_remnashop_user_state"},
            {log.event_type for log in target.added},
        )

    async def test_referral_import_links_users_and_records_mapping(self):
        source = _FakeSourceConnection(
            {
                "referrals": [
                    {"id": 7, "referrer_telegram_id": 111, "referred_telegram_id": 222},
                    {"id": 8, "referrer_telegram_id": 111, "referred_telegram_id": 111},
                ]
            }
        )
        target = _FakeTargetSession()
        importer = self._importer(source, target, only={"referrals"})
        importer.tables = {"referrals"}

        users = {
            111: SimpleNamespace(user_id=111, referred_by_id=None),
            222: SimpleNamespace(user_id=222, referred_by_id=None),
        }

        async def fake_get_user_by_telegram_id(session, telegram_id):
            return users.get(telegram_id)

        with mock.patch.object(user_dal, "get_user_by_telegram_id", fake_get_user_by_telegram_id):
            await importer.import_referrals()

        self.assertEqual(111, users[222].referred_by_id)
        self.assertEqual(1, importer.summary["referrals"]["updated"])
        self.assertEqual(1, importer.summary["referrals"]["skipped"])

        mapping_inserts = target.inserts("legacy_import_mappings")
        self.assertEqual(1, len(mapping_inserts))
        params = _insert_params(mapping_inserts[0])
        self.assertEqual("referral", params["entity_type"])
        self.assertEqual("7", params["source_id"])
        self.assertEqual("users", params["target_table"])
        self.assertEqual("222", params["target_id"])
