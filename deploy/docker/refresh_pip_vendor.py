"""Remove the optional legacy metadata backend from the Python 3.12 image's pip wheel.

Run on the unpacked upstream wheel before repacking so RECORD covers the actual files.
Remove this customization once upstream pip drops its bundled pkg_resources.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise ValueError(f"Recheck the upstream pip wheel: {path}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def main(wheel_root: Path) -> None:
    vendor = wheel_root / "pip" / "_vendor"
    metadata = wheel_root / "pip" / "_internal" / "metadata"

    # Use pip's standard importlib backend even when a caller requests its old backend.
    replace_once(
        metadata / "__init__.py",
        "if _should_use_importlib_metadata():",
        "if sys.version_info >= (3, 12) or _should_use_importlib_metadata():",
    )
    (metadata / "pkg_resources.py").unlink()
    shutil.rmtree(vendor / "pkg_resources")
    replace_once(vendor / "__init__.py", '    vendored("pkg_resources")\n', "")
    replace_once(vendor / "vendor.txt", "setuptools==70.3.0\n", "")

    inventory = vendor / "bom.cdx.json"
    bom = json.loads(inventory.read_text(encoding="utf-8"))
    (removed,) = [item for item in bom["components"] if item["name"] == "setuptools"]
    bom["components"].remove(removed)
    reference = removed["bom-ref"]
    bom["dependencies"] = [item for item in bom["dependencies"] if item["ref"] != reference]
    for item in bom["dependencies"]:
        if reference in item.get("dependsOn", []):
            item["dependsOn"].remove(reference)
    inventory.write_text(json.dumps(bom, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
