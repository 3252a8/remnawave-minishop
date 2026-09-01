"""Generated documentation helpers for domain event payload contracts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import UnionType
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel

from bot.infra import event_payloads, events

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_PATH = REPO_ROOT / "docs" / "architecture" / "events.md"
TRANSLATIONS_PATH = Path(__file__).with_name("event_catalog.ru.json")
_CANONICAL_EMITTER_PATHS = {
    "backend/bot/app/web/webapp/auth_referral.py": "backend/bot/app/web/webapp/auth.py",
    "backend/bot/app/web/webapp/billing_status.py": "backend/bot/app/web/webapp/billing.py",
    "backend/bot/handlers/user/start_flow.py": "backend/bot/handlers/user/start.py",
    "backend/bot/payment_providers/yookassa/success.py": (
        "backend/bot/payment_providers/yookassa.py"
    ),
    "backend/bot/payment_providers/yookassa/success_helpers.py": (
        "backend/bot/payment_providers/yookassa.py"
    ),
    "backend/bot/payment_providers/yookassa/webhook.py": (
        "backend/bot/payment_providers/yookassa.py"
    ),
}


def _event_models() -> list[type[event_payloads.EventPayload]]:
    models = [
        value
        for value in vars(event_payloads).values()
        if (
            isinstance(value, type)
            and issubclass(value, event_payloads.EventPayload)
            and value is not event_payloads.EventPayload
        )
    ]
    return sorted(models, key=lambda model: model.EVENT_NAME)


def _format_type(annotation: Any) -> str:
    origin = get_origin(annotation)
    if origin is None:
        if annotation is type(None):
            return "None"
        if isinstance(annotation, type):
            return annotation.__name__
        return str(annotation).replace("typing.", "")
    args = get_args(annotation)
    if origin in {Union, UnionType}:
        return " | ".join(_format_type(arg) for arg in args)
    if str(origin) == "typing.Literal":
        return " | ".join(repr(arg) for arg in args)
    return str(annotation).replace("typing.", "")


def _load_text() -> dict[str, str]:
    payload = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in payload.items()
    ):
        raise RuntimeError("Event catalog translations must be a string dictionary.")
    return payload


def _default_text(field: Any, text: dict[str, str]) -> str:
    if field.is_required():
        return text["required"]
    default = field.default
    if default is None:
        return "`None`"
    return f"`{default!r}`"


def _field_rows(model: type[BaseModel], text: dict[str, str]) -> list[str]:
    rows = [text["field_header"], "| --- | --- | --- |"]
    for name, field in model.model_fields.items():
        rows.append(
            f"| `{name}` | `{_format_type(field.annotation)}` | {_default_text(field, text)} |"
        )
    return rows


def _discover_emitters(models: list[type[event_payloads.EventPayload]]) -> dict[str, list[str]]:
    model_names = {model.__name__: model.EVENT_NAME for model in models}
    emitters: dict[str, set[str]] = {model.EVENT_NAME: set() for model in models}
    for path in sorted((REPO_ROOT / "backend").rglob("*.py")):
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative in {
            "backend/bot/infra/event_payloads.py",
            "backend/bot/infra/event_catalog.py",
        }:
            continue
        source = path.read_text(encoding="utf-8")
        for model_name, event_name in model_names.items():
            if model_name in source:
                emitters[event_name].add(_CANONICAL_EMITTER_PATHS.get(relative, relative))
    return {event_name: sorted(paths) for event_name, paths in emitters.items()}


def _discover_core_reactions() -> dict[str, list[str]]:
    source = (REPO_ROOT / "backend" / "bot" / "services" / "event_reactions.py").read_text(
        encoding="utf-8"
    )
    reactions: dict[str, list[str]] = {}
    pattern = r"\(\s*events\.([A-Z_]+),\s*reactions\.([a-z_]+)\s*\)"
    for constant, handler in re.findall(pattern, source):
        event_name = getattr(events, constant, None)
        if event_name:
            reactions.setdefault(event_name, []).append(f"CoreEventReactions.{handler}")
    return {event_name: sorted(handlers) for event_name, handlers in reactions.items()}


def generate_event_catalog_markdown() -> str:
    text = _load_text()
    models = _event_models()
    emitters = _discover_emitters(models)
    reactions = _discover_core_reactions()
    lines = [
        text["title"],
        "",
        text["generated"],
        text["regenerate"],
        "",
        text["intro"],
        "",
    ]
    for model in models:
        lines.extend(
            [
                f"## `{model.EVENT_NAME}`",
                "",
                text["payload_model"].format(model=model.__name__),
                "",
                text["emitters"]
                + (
                    ", ".join(f"`{path}`" for path in emitters.get(model.EVENT_NAME, ()))
                    or text["emitters_none"]
                ),
                "",
                text["reactions"]
                + (
                    ", ".join(f"`{handler}`" for handler in reactions.get(model.EVENT_NAME, ()))
                    or text["reactions_none"]
                ),
                "",
                *_field_rows(model, text),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_event_catalog(path: Path = DEFAULT_OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_event_catalog_markdown(), encoding="utf-8")


def main() -> None:
    write_event_catalog()
    print(f"Wrote {DEFAULT_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
