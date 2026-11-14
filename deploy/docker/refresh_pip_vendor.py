"""Refresh pip's bundled pkg_resources until upstream includes the fixes.

Remove this helper once pip vendors pkg_resources from setuptools >= 80.9.0
or removes that legacy backend.
"""

from __future__ import annotations

import importlib.metadata
import json
import shutil
import sys
from pathlib import Path

import pip


def replace(path: Path, old: str, new: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != count:
        raise RuntimeError(f"Upstream vendoring patch no longer matches {path}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def main(source: Path) -> None:
    if pip.__version__ != "26.3" or pip.__file__ is None:
        raise RuntimeError("Recheck the vendoring patches for this pip version")
    vendor = Path(pip.__file__).parent / "_vendor"
    resources_dir = vendor / "pkg_resources"
    shutil.rmtree(resources_dir)
    shutil.copytree(
        source / "pkg_resources", resources_dir, ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copy2(
        source / "setuptools-80.9.0.dist-info" / "licenses" / "LICENSE", resources_dir / "LICENSE"
    )

    manifest = vendor / "vendor.txt"
    replace(manifest, "setuptools==70.3.0", "setuptools==80.9.0")

    # pip ships a CycloneDX inventory too; preserve it with accurate versions and
    # dependency references so SBOM consumers see the same libraries as Python.
    inventory = vendor / "bom.cdx.json"
    bom = json.loads(inventory.read_text(encoding="utf-8"))
    components = [component for component in bom["components"] if component["name"] == "setuptools"]
    if len(components) != 1:
        raise RuntimeError("Expected one setuptools component in pip's SBOM")
    component = components[0]
    reference = "pkg:pypi/setuptools@80.9.0"
    references = {component["bom-ref"]: reference}
    component.update({"version": "80.9.0", "purl": reference, "bom-ref": reference})
    for dependency in bom["dependencies"]:
        dependency["ref"] = references.get(dependency["ref"], dependency["ref"])
        if "dependsOn" in dependency:
            dependency["dependsOn"] = [
                references.get(reference, reference) for reference in dependency["dependsOn"]
            ]
    inventory.write_text(json.dumps(bom, indent=2) + "\n", encoding="utf-8")

    resources = resources_dir / "__init__.py"
    text = resources.read_text(encoding="utf-8")
    for name in ("markers", "requirements", "specifiers", "utils", "version"):
        old = f"import packaging.{name}"
        if text.count(old) != 1:
            raise RuntimeError(f"Recheck pkg_resources packaging.{name} imports")
        text = text.replace(old, f"from pip._vendor.packaging import {name} as _packaging_{name}")
        text = text.replace(f"packaging.{name}.", f"_packaging_{name}.")
    resources.write_text(text, encoding="utf-8")
    replace(
        resources,
        "from jaraco.text import drop_comment, join_continuation, yield_lines",
        "from pip._internal.utils._jaraco_text import drop_comment, join_continuation, yield_lines",
    )
    replace(
        resources,
        "from platformdirs import user_cache_dir as _user_cache_dir",
        "from pip._vendor.platformdirs import user_cache_dir as _user_cache_dir",
    )
    replace(
        resources,
        "sys.path.extend(((vendor_path := os.path.join(os.path.dirname(os.path.dirname(__file__)), "
        "'setuptools', '_vendor')) not in sys.path) * [vendor_path])  # fmt: skip\n"
        "# workaround for #4476\nsys.modules.pop('backports', None)",
        "",
    )
    replace(
        resources,
        "warnings.warn(\n"
        '    "pkg_resources is deprecated as an API. "\n'
        '    "See https://setuptools.pypa.io/en/latest/pkg_resources.html. "\n'
        '    "The pkg_resources package is slated for removal as early as "\n'
        '    "2025-11-30. Refrain from using this package or pin to "\n'
        '    "Setuptools<81.",\n    UserWarning,\n    stacklevel=2,\n)',
        "",
    )
    # CVE-2025-47273 affects setuptools.package_index, which pip does not vendor.
    # Preserve that boundary while refreshing pkg_resources independently.
    if (vendor / "setuptools").exists():
        raise RuntimeError("Recheck the setuptools vendoring boundary")
    try:
        setuptools_version = importlib.metadata.version("setuptools")
    except importlib.metadata.PackageNotFoundError:
        pass
    else:
        if setuptools_version == "70.3.0":
            raise RuntimeError("The full vulnerable setuptools package must not be installed")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
