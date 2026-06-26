from __future__ import annotations

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
