from __future__ import annotations

import fnmatch
import importlib.util
import json
from pathlib import Path
from types import ModuleType


def _load_check_architecture() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "check_architecture.py"
    spec = importlib.util.spec_from_file_location("check_architecture_under_test", path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_architecture = _load_check_architecture()


def _base_config() -> dict[str, object]:
    return {
        "module_size": {
            "max_lines": 1000,
            "scopes": [],
            "extensions": [".py", ".ts", ".svelte", ".js"],
            "allowlist": [],
        },
        "type_ignore": {
            "scopes": [],
            "allowlist": {},
        },
        "raw_json_response": {
            "scopes": [],
            "allowlist": [],
        },
    }


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_check(
    tmp_path: Path,
    monkeypatch,
    capsys,
    config: dict[str, object],
) -> tuple[int, str]:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    config_path = scripts_dir / "architecture_gates.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    monkeypatch.setattr(check_architecture, "ROOT", tmp_path)
    monkeypatch.setattr(check_architecture, "CONFIG_PATH", config_path)

    result = check_architecture.main()
    output = capsys.readouterr().out
    return result, output


def test_architecture_check_passes_empty_scopes(tmp_path, monkeypatch, capsys) -> None:
    result, output = _run_check(tmp_path, monkeypatch, capsys, _base_config())

    assert result == 0
    assert "Architecture checks passed." in output


def test_module_size_guard_rejects_new_oversized_modules(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    config = _base_config()
    config["module_size"] = {
        "max_lines": 2,
        "scopes": ["backend/bot"],
        "extensions": [".py"],
        "allowlist": [],
    }
    _write(tmp_path, "backend/bot/too_large.py", "one\ntwo\nthree\n")

    result, output = _run_check(tmp_path, monkeypatch, capsys, config)

    assert result == 1
    assert "[module-size]" in output
    assert "backend/bot/too_large.py" in output


def test_type_ignore_guard_rejects_new_backend_ignores(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    config = _base_config()
    config["type_ignore"] = {
        "scopes": ["backend/bot"],
        "allowlist": {},
    }
    _write(tmp_path, "backend/bot/ignored.py", "value = 1  # type: ignore[assignment]\n")

    result, output = _run_check(tmp_path, monkeypatch, capsys, config)

    assert result == 1
    assert "[type-ignore]" in output
    assert "backend/bot/ignored.py" in output


def test_raw_json_response_guard_rejects_unwrapped_aiohttp_responses(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    config = _base_config()
    config["raw_json_response"] = {
        "scopes": ["backend/bot/app/web/webapp"],
        "allowlist": [],
    }
    _write(
        tmp_path,
        "backend/bot/app/web/webapp/raw_response.py",
        "from aiohttp import web\n\nresponse = web.json_response({})\n",
    )

    result, output = _run_check(tmp_path, monkeypatch, capsys, config)

    assert result == 1
    assert "[raw-json-response]" in output
    assert "backend/bot/app/web/webapp/raw_response.py" in output


def test_frontend_weak_typing_guard_rejects_as_any(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    config = _base_config()
    config["frontend_weak_typing"] = {
        "scopes": ["frontend/src"],
        "extensions": [".ts"],
        "allowlist": [],
    }
    _write(tmp_path, "frontend/src/weak.ts", "const value = raw as any;\n")

    result, output = _run_check(tmp_path, monkeypatch, capsys, config)

    assert result == 1
    assert "[frontend-weak-typing]" in output
    assert "frontend/src/weak.ts" in output


def test_frontend_weak_typing_guard_rejects_any_action_callbacks(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    config = _base_config()
    config["frontend_weak_typing"] = {
        "scopes": ["frontend/src"],
        "extensions": [".svelte"],
        "allowlist": [],
    }
    _write(
        tmp_path,
        "frontend/src/coordinator.svelte",
        "<script>type Action = (...args: any[]) => any;</script>\n",
    )

    result, output = _run_check(tmp_path, monkeypatch, capsys, config)

    assert result == 1
    assert "[frontend-weak-typing]" in output
    assert "frontend/src/coordinator.svelte" in output


def test_frontend_weak_typing_guard_rejects_any_annotations(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    config = _base_config()
    config["frontend_weak_typing"] = {
        "scopes": ["frontend/src"],
        "extensions": [".ts"],
        "allowlist": [],
    }
    _write(tmp_path, "frontend/src/annotation.ts", "let value: any = raw;\n")

    result, output = _run_check(tmp_path, monkeypatch, capsys, config)

    assert result == 1
    assert "[frontend-weak-typing]" in output
    assert "frontend/src/annotation.ts" in output


def test_frontend_weak_typing_guard_enforces_baseline_counts(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    config = _base_config()
    config["frontend_weak_typing"] = {
        "scopes": ["frontend/src"],
        "extensions": [".svelte"],
        "allowlist": [],
        "allowed_counts": {"frontend/src/legacy.svelte": 1},
    }
    _write(
        tmp_path,
        "frontend/src/legacy.svelte",
        "<script>const first = raw as any; const second = raw as any;</script>\n",
    )

    result, output = _run_check(tmp_path, monkeypatch, capsys, config)

    assert result == 1
    assert "[frontend-weak-typing]" in output
    assert "frontend/src/legacy.svelte" in output
    assert "allowed 1" in output


def test_first_party_js_guard_rejects_new_js_files(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    config = _base_config()
    config["first_party_js"] = {
        "scopes": ["frontend/src"],
        "allowlist": ["frontend/src/generated.js"],
    }
    _write(tmp_path, "frontend/src/generated.js", "export const generated = true;\n")
    _write(tmp_path, "frontend/src/handwritten.js", "export const handwritten = true;\n")

    result, output = _run_check(tmp_path, monkeypatch, capsys, config)

    assert result == 1
    assert "[first-party-js]" in output
    assert "frontend/src/handwritten.js" in output
    assert "frontend/src/generated.js" not in output


def test_first_party_js_guard_rejects_stale_allowlist_entries(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    config = _base_config()
    config["first_party_js"] = {
        "scopes": ["frontend/src"],
        "allowlist": ["frontend/src/removed.js"],
    }
    _write(tmp_path, "frontend/src/typed.ts", "export const typed = true;\n")

    result, output = _run_check(tmp_path, monkeypatch, capsys, config)

    assert result == 1
    assert "[first-party-js]" in output
    assert "allowlist entry is stale" in output


def test_svelte_lang_ts_guard_rejects_new_untyped_svelte(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    config = _base_config()
    config["svelte_lang_ts"] = {
        "scopes": ["frontend/src"],
        "allowlist": [],
    }
    _write(tmp_path, "frontend/src/new-widget.svelte", "<script>let value = 1;</script>\n")

    result, output = _run_check(tmp_path, monkeypatch, capsys, config)

    assert result == 1
    assert "[svelte-lang-ts]" in output
    assert "frontend/src/new-widget.svelte" in output


def test_svelte_lang_ts_guard_rejects_stale_allowlist_entries(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    config = _base_config()
    config["svelte_lang_ts"] = {
        "scopes": ["frontend/src"],
        "allowlist": ["frontend/src/legacy.svelte"],
    }
    _write(tmp_path, "frontend/src/legacy.svelte", '<script lang="ts">let value = 1;</script>\n')

    result, output = _run_check(tmp_path, monkeypatch, capsys, config)

    assert result == 1
    assert "[svelte-lang-ts]" in output
    assert "allowlist entry is stale" in output


def test_frontend_api_guard_rejects_untyped_api_paths(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    config = _base_config()
    config["frontend_api_calls"] = {
        "scopes": ["frontend/src"],
        "allowed_calls": ["apiUnchecked"],
        "allowlist_paths": [],
    }
    _write(tmp_path, "frontend/src/api-bypass.ts", 'api("/api/admin/users");\n')

    result, output = _run_check(tmp_path, monkeypatch, capsys, config)

    assert result == 1
    assert "[frontend-api-path]" in output
    assert "frontend/src/api-bypass.ts" in output


def test_route_contract_guard_rejects_uncovered_api_routes(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    config = _base_config()
    config["route_contracts"] = {
        "route_setup_scopes": ["backend/bot/app/web/webapp/routes.py"],
        "contract_scopes": ["backend/bot/app/web/webapp/routes.py"],
        "path_allowlist": [],
    }
    _write(
        tmp_path,
        "backend/bot/app/web/webapp/routes.py",
        """
async def profile_route(request):
    return None


def setup_routes(app):
    app.router.add_get("/api/profile", profile_route)
""",
    )

    result, output = _run_check(tmp_path, monkeypatch, capsys, config)

    assert result == 1
    assert "[route-contracts]" in output
    assert "/api/profile" in output


def test_route_contract_guard_accepts_decentralized_contracts(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    config = _base_config()
    config["route_contracts"] = {
        "route_setup_scopes": ["backend/bot/app/web/webapp/routes.py"],
        "contract_scopes": ["backend/bot/app/web/webapp"],
        "path_allowlist": [],
    }
    _write(
        tmp_path,
        "backend/bot/app/web/webapp/routes.py",
        """
async def profile_route(request):
    return None


def setup_routes(app):
    app.router.add_get("/api/profile", profile_route)
""",
    )
    _write(
        tmp_path,
        "backend/bot/app/web/webapp/profile_contracts.py",
        'PROFILE_ROUTE_CONTRACTS = {"profile_route": object()}\n',
    )

    result, output = _run_check(tmp_path, monkeypatch, capsys, config)

    assert result == 0
    assert "Architecture checks passed." in output


def test_loose_schema_guard_rejects_unexplained_loose_contracts(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    config = _base_config()
    config["loose_schemas"] = {
        "scopes": ["backend/bot/app/web/webapp"],
        "allowlist": {},
    }
    _write(
        tmp_path,
        "backend/bot/app/web/webapp/profile_contracts.py",
        "from bot.app.web.route_contracts import loose_object_schema\n"
        "PROFILE_ROUTE_CONTRACTS = {'profile_route': loose_object_schema()}\n",
    )

    result, output = _run_check(tmp_path, monkeypatch, capsys, config)

    assert result == 1
    assert "[loose-schema]" in output
    assert "profile_contracts.py" in output


def test_loose_schema_guard_requires_non_empty_reasons(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    config = _base_config()
    config["loose_schemas"] = {
        "scopes": ["backend/bot/app/web/webapp"],
        "allowlist": {
            "backend/bot/app/web/webapp/profile_contracts.py": {
                "loose_object_schema": [""],
            }
        },
    }
    _write(
        tmp_path,
        "backend/bot/app/web/webapp/profile_contracts.py",
        "from bot.app.web.route_contracts import loose_object_schema\n"
        "PROFILE_ROUTE_CONTRACTS = {'profile_route': loose_object_schema()}\n",
    )

    result, output = _run_check(tmp_path, monkeypatch, capsys, config)

    assert result == 1
    assert "reason #1 is empty" in output


# ---------------------------------------------------------------------------
# Real-config lock: the module-size allowlist may exempt generated artifacts only.
#
# The module-size gate exempts a small allowlist from the line limit. Every entry
# must name a *generated* build output, never hand-written code that grew too large
# (that has to be split). The patterns below are the sanctioned generated artifacts,
# each annotated with the generator that emits it. A future allowlist entry has to
# match one of them, so adding a hand-written file to the allowlist fails this test
# rather than merely inviting a reviewer's objection.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

GENERATED_ARTIFACT_PATTERNS: dict[str, str] = {
    "backend/bot/app/web/templates/*.js": (
        "compiled webapp/admin Svelte bundles emitted by the frontend build"
    ),
    "frontend/src/lib/api/openapi.generated.ts": (
        "typed API client generated from docs/openapi.json (npm run generate:api-types)"
    ),
    "frontend/src/lib/webapp/demoDataset.js": (
        "demo dataset snapshot; its file header marks it generated"
    ),
}


def _is_documented_generated_artifact(entry: str) -> bool:
    return any(
        entry == pattern or fnmatch.fnmatch(entry, pattern)
        for pattern in GENERATED_ARTIFACT_PATTERNS
    )


def test_module_size_allowlist_is_generated_artifacts_only() -> None:
    config = json.loads(
        (REPO_ROOT / "scripts" / "architecture_gates.json").read_text(encoding="utf-8")
    )
    allowlist = config["module_size"]["allowlist"]

    undocumented = [entry for entry in allowlist if not _is_documented_generated_artifact(entry)]
    assert not undocumented, (
        "module_size.allowlist may only exempt generated artifacts; these entries match "
        f"no documented generator pattern (split the module instead): {undocumented}"
    )
