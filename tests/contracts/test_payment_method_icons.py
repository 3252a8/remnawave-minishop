"""Every icon advertised by a payment provider must exist in the Mini App bundle."""

import re
from pathlib import Path

from bot.payment_providers.registry import PAYMENT_PROVIDER_SPECS

REPO_ROOT = Path(__file__).resolve().parents[2]
ICON_EXPORT = re.compile(r"^  ([A-Z][A-Za-z0-9]*),$", re.MULTILINE)


def test_provider_icons_are_exported_to_the_mini_app() -> None:
    # PaymentMethodPicker resolves spec.webapp_icon through this explicit export.
    source = (REPO_ROOT / "frontend/src/lib/components/ui/icons.ts").read_text(encoding="utf-8")
    exported = set(ICON_EXPORT.findall(source))
    assert exported

    missing = {
        spec.id: spec.webapp_icon
        for spec in PAYMENT_PROVIDER_SPECS
        if spec.webapp_icon and spec.webapp_icon not in exported
    }
    assert not missing, f"payment method icons unavailable in the Mini App: {missing}"
