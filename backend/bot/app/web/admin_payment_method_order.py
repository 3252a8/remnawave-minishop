"""Admin-facing metadata for the legacy PAYMENT_METHODS_ORDER string setting."""

from __future__ import annotations

from typing import Any

from bot.payment_providers import iter_provider_specs, resolve_provider_presentation
from config.settings import Settings


def payment_method_order_options(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Describe every ordered checkout button without changing the string contract."""

    specs = list(iter_provider_specs())
    specs_by_id = {spec.id: spec for spec in specs}
    configured_order = settings.payment_methods_order if settings is not None else []
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for raw_method in (*configured_order, *(spec.id for spec in specs)):
        method = str(raw_method or "").strip().lower()
        if not method or method in seen:
            continue
        seen.add(method)
        ordered_ids.append(method)

    options: list[dict[str, Any]] = []
    for method in ordered_ids:
        spec = specs_by_id.get(method)
        if spec is None:
            # Removed/plugin-owned methods stay visible and sortable so saving
            # from a newer or older Core never silently erases the operator's value.
            options.append(
                {
                    "id": method,
                    "label": method,
                    "provider_id": method,
                    "provider_label": method,
                    "enabled": False,
                    "admin_only": False,
                    "known": False,
                }
            )
            continue

        public_enabled = spec.is_enabled(settings) if settings is not None else False
        admin_only_enabled = spec.is_admin_only_enabled(settings) if settings is not None else False
        options.append(
            {
                "id": spec.id,
                "label": resolve_provider_presentation(spec, settings).webapp_label,
                "provider_id": spec.provider_key,
                "provider_label": spec.label,
                "enabled": public_enabled or admin_only_enabled,
                "admin_only": admin_only_enabled and not public_enabled,
                "known": True,
            }
        )
    return options
