"""Generate the human Remnawave compatibility catalog from runtime contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bot.services.panel_api_contracts import (
    PANEL_API_OPERATION_CONTRACTS,
    PANEL_WEBHOOK_CONTRACTS,
    load_support_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_PATH = REPO_ROOT / "docs" / "architecture" / "remnawave-api-compatibility.md"
TRANSLATIONS_PATH = Path(__file__).with_name("panel_api_catalog.ru.json")


def _load_text() -> dict[str, Any]:
    payload = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Panel API catalog translations must contain a JSON object.")
    return payload


def _text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise RuntimeError(f"Panel API catalog translation {key!r} must be a string.")
    return value


def _lines(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeError(f"Panel API catalog translation {key!r} must be a string list.")
    return value


def _mapping(payload: dict[str, Any], key: str) -> dict[str, str]:
    value = payload.get(key)
    if not isinstance(value, dict) or not all(
        isinstance(item_key, str) and isinstance(item_value, str)
        for item_key, item_value in value.items()
    ):
        raise RuntimeError(f"Panel API catalog translation {key!r} must be a string map.")
    return value


def _localized(mapping: dict[str, str], value: object, context: str) -> str:
    source = str(value)
    try:
        return mapping[source]
    except KeyError as exc:
        raise RuntimeError(f"Missing Russian translation for {context}: {source}") from exc


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _generation_names(values: object) -> str:
    if not isinstance(values, (list, tuple)):
        return "—"
    return ", ".join(str(getattr(value, "value", value)) for value in values) or "—"


def generate_remnawave_api_markdown() -> str:
    manifest = load_support_manifest()
    policy = manifest["policy"]
    generations = manifest["generations"]
    historical = manifest["historical_versions"]
    upgrades = manifest["upgrade_paths"]
    text = _load_text()
    status_labels = _mapping(text, "status_labels")
    historical_reasons = _mapping(text, "historical_reasons")
    response_shapes = _mapping(text, "response_shapes")
    compatibility_notes = _mapping(text, "compatibility_notes")
    strategy_labels = _mapping(text, "strategy_labels")
    webhook_text = text.get("webhooks")
    if not isinstance(webhook_text, dict):
        raise RuntimeError("Panel API catalog translation 'webhooks' must be an object.")

    policy_values = {
        "supported_api_generations": policy["supported_api_generations"],
        "deprecation_minimum_days": policy["deprecation_minimum_days"],
        "deprecation_minimum_core_releases": policy["deprecation_minimum_core_releases"],
    }
    lines = [
        _text(text, "title"),
        "",
        _text(text, "generated_comment"),
        "",
        *_lines(text, "intro"),
        "",
        _text(text, "support_heading"),
        "",
        *(line.format(**policy_values) for line in _lines(text, "support_policy")),
        "",
        *_lines(text, "best_effort"),
        "",
        _text(text, "certified_heading"),
        "",
        _text(text, "certified_header"),
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in generations:
        upstream = str(item["upstream_release"])
        lines.append(
            "| "
            + " | ".join(
                (
                    _cell(_localized(status_labels, item["status"], "support status")),
                    _cell(item["id"]),
                    _cell(", ".join(item["certified_versions"])),
                    _cell(item["preset"]),
                    _cell(", ".join(item["capabilities"]) or "—"),
                    _cell(", ".join(item["coverage"])),
                    f"[{_text(text, 'release_notes')}]({upstream})",
                )
            )
            + " |"
        )

    lines.extend(["", *_lines(text, "historical_intro"), ""])
    lines.extend(
        f"- `{item['version']}` — "
        f"{_localized(historical_reasons, item['reason'], 'historical preset reason')}"
        for item in historical
    )

    lines.extend(
        [
            "",
            _text(text, "operations_heading"),
            "",
            *_lines(text, "operations_intro"),
            "",
            _text(text, "operations_header"),
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for contract in PANEL_API_OPERATION_CONTRACTS:
        response = _localized(
            response_shapes,
            contract.response_shape,
            f"response shape for {contract.operation.value}",
        )
        if contract.empty_success_body:
            response += _text(text, "empty_success_body")
        compatibility = _localized(
            compatibility_notes,
            contract.compatibility_note,
            f"compatibility note for {contract.operation.value}",
        )
        lines.append(
            "| "
            + " | ".join(
                (
                    f"`{contract.operation.value}`",
                    contract.method,
                    f"`{_cell(contract.path)}`",
                    _generation_names(contract.generations),
                    ", ".join(str(value) for value in contract.success_statuses),
                    _cell(response),
                    _cell(compatibility),
                    _generation_names(contract.coverage),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            _text(text, "webhooks_heading"),
            "",
            _text(text, "webhooks_header"),
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for contract in PANEL_WEBHOOK_CONTRACTS:
        localized = webhook_text.get(contract.event)
        if not isinstance(localized, dict) or not all(
            isinstance(localized.get(key), str) for key in ("event", "identity", "behavior")
        ):
            raise RuntimeError(f"Missing Russian webhook translation for {contract.event}")
        lines.append(
            "| "
            + " | ".join(
                (
                    _cell(localized["event"]),
                    _generation_names(contract.generations),
                    _cell(localized["identity"]),
                    _cell(localized["behavior"]),
                    _generation_names(contract.coverage),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            _text(text, "upgrades_heading"),
            "",
            _text(text, "upgrades_header"),
            "| --- | --- | --- | --- |",
        ]
    )
    lines.extend(
        (
            f"| {item['from']} | {item['to']} | "
            f"{_localized(strategy_labels, item['strategy'], 'upgrade strategy')} | "
            f"`{item['verification']}` |"
        )
        for item in upgrades
    )

    lines.extend(
        [
            "",
            _text(text, "rules_heading"),
            "",
            *_lines(text, "rules"),
            "",
            _text(text, "checklist_heading"),
            "",
            *_lines(text, "checklist"),
            "",
            _text(text, "manifest_review").format(reviewed_at=manifest["reviewed_at"]),
            "",
        ]
    )
    return "\n".join(line.rstrip() for line in lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the generated file drifts")
    args = parser.parse_args()
    generated = generate_remnawave_api_markdown()
    if args.check:
        actual = DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        if actual != generated:
            raise SystemExit(f"{DEFAULT_OUTPUT_PATH} is stale; regenerate the catalog")
        return
    DEFAULT_OUTPUT_PATH.write_text(generated, encoding="utf-8")


if __name__ == "__main__":
    main()
