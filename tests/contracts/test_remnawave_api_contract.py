from __future__ import annotations

import ast
import json
from pathlib import Path

from bot.services.panel_api_catalog import (
    DEFAULT_OUTPUT_PATH,
    generate_remnawave_api_markdown,
)
from bot.services.panel_api_compat import PanelApiCompatibility, normalize_panel_user
from bot.services.panel_api_contracts import (
    PANEL_API_OPERATION_CONTRACTS,
    PanelApiOperation,
    load_support_manifest,
)

ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = ROOT / "backend" / "bot" / "services"
PANEL_CALL_MODULES = (
    "panel_api_core.py",
    "panel_api_users.py",
    "panel_api_resources.py",
    "panel_api_squads.py",
)


def test_generated_remnawave_catalog_is_current() -> None:
    assert DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8") == generate_remnawave_api_markdown()


def test_every_panel_request_declares_a_registered_operation() -> None:
    for filename in PANEL_CALL_MODULES:
        path = SERVICE_ROOT / filename
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_request"
            ):
                continue
            operation_keywords = [
                keyword for keyword in node.keywords if keyword.arg == "operation"
            ]
            assert operation_keywords, f"{filename}:{node.lineno} has no PanelApiOperation"


def test_operation_registry_is_complete_and_consistent() -> None:
    assert {contract.operation for contract in PANEL_API_OPERATION_CONTRACTS} == set(
        PanelApiOperation
    )
    assert len({contract.operation for contract in PANEL_API_OPERATION_CONTRACTS}) == len(
        PANEL_API_OPERATION_CONTRACTS
    )
    for contract in PANEL_API_OPERATION_CONTRACTS:
        assert contract.method in {"GET", "POST", "PATCH", "DELETE"}
        assert contract.path.startswith("/")
        assert contract.log_label.startswith("/")
        assert contract.generations
        assert contract.success_statuses
        assert contract.coverage
        if contract.empty_success_body:
            assert any(status in {202, 204} for status in contract.success_statuses)


def test_support_manifest_matches_presets_and_policy() -> None:
    manifest = load_support_manifest()
    generations = manifest["generations"]
    assert [item["status"] for item in generations] == ["current", "maintenance"]
    assert len(generations) == manifest["policy"]["supported_api_generations"] == 2

    certified = {version for item in generations for version in item["certified_versions"]}
    assert certified == {"2.8.1", "3.0.0", "3.1.0", "3.2.0", "3.2.1"}
    for item in generations:
        preset = ROOT / "deploy" / "dev" / "remnawave-stands" / item["preset"]
        assert preset.is_dir()
        for version in item["certified_versions"]:
            version_preset = ROOT / "deploy" / "dev" / "remnawave-stands" / version
            fixture = ROOT / "tests" / "fixtures" / "remnawave" / version / "contract.json"
            assert version_preset.is_dir()
            assert fixture.is_file()

    for upgrade in manifest["upgrade_paths"]:
        assert upgrade["from"] in certified
        assert upgrade["to"] in certified
        assert (ROOT / upgrade["verification"]).is_file()


def test_certified_version_fixtures_match_runtime_adapter() -> None:
    fixture_root = ROOT / "tests" / "fixtures" / "remnawave"
    for path in sorted(fixture_root.glob("*/contract.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        compatibility = PanelApiCompatibility.from_metadata(payload["metadata"])
        normalized = normalize_panel_user(payload["user"])
        expected = payload["expected"]

        assert compatibility.version == path.parent.name
        assert compatibility.generation.value == expected["generation"]
        assert compatibility.support_status == expected["support_status"]
        assert (
            sorted(capability.value for capability in compatibility.capabilities)
            == expected["capabilities"]
        )
        assert normalized is not None
        assert normalized["uuid"] == expected["identity_alias"]
