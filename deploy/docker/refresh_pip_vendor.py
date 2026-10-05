"""Refresh pip's bundled libraries until an upstream release includes these fixes.

Keep pip's namespace/Brotli patches and pure-Python msgpack layout, as documented
at https://pip.pypa.io/en/stable/development/vendoring-policy/.
Remove this helper once upstream pip vendors urllib3 >= 2.8.0 and msgpack >= 1.2.1.
"""

from __future__ import annotations

import importlib.metadata
import json
import re
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
    if pip.__version__ != "26.2.1" or pip.__file__ is None:
        raise RuntimeError("Recheck the vendoring patches for this pip version")
    vendor = Path(pip.__file__).parent / "_vendor"
    for name, version, license_name in (
        ("urllib3", "2.8.0", "LICENSE.txt"),
        ("msgpack", "1.2.1", "COPYING"),
    ):
        shutil.rmtree(vendor / name)
        shutil.copytree(
            source / name,
            vendor / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.so", "*.pyd"),
        )
        shutil.copy2(
            source / f"{name}-{version}.dist-info" / "licenses" / license_name,
            vendor / name / license_name,
        )
        manifest = vendor / "vendor.txt"
        text = manifest.read_text(encoding="utf-8")
        text, count = re.subn(rf"(?m)^(\s*){name}==[^\n]+$", rf"\g<1>{name}=={version}", text)
        if count != 1:
            raise RuntimeError(f"Expected one {name} entry in pip's vendor manifest")
        manifest.write_text(text, encoding="utf-8")

    # pip ships a CycloneDX inventory too; preserve it with accurate versions and
    # dependency references so SBOM consumers see the same libraries as Python.
    inventory = vendor / "bom.cdx.json"
    bom = json.loads(inventory.read_text(encoding="utf-8"))
    references: dict[str, str] = {}
    for name, version in (("urllib3", "2.8.0"), ("msgpack", "1.2.1")):
        components = [component for component in bom["components"] if component["name"] == name]
        if len(components) != 1:
            raise RuntimeError(f"Expected one {name} component in pip's SBOM")
        component = components[0]
        reference = f"pkg:pypi/{name}@{version}"
        references[component["bom-ref"]] = reference
        component.update({"version": version, "purl": reference, "bom-ref": reference})
    for dependency in bom["dependencies"]:
        dependency["ref"] = references.get(dependency["ref"], dependency["ref"])
        if "dependsOn" in dependency:
            dependency["dependsOn"] = [
                references.get(reference, reference) for reference in dependency["dependsOn"]
            ]
    inventory.write_text(json.dumps(bom, indent=2) + "\n", encoding="utf-8")

    # Preserve pip's vendoring transformations, including imports inside docstrings.
    for path in (vendor / "urllib3").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"(?m)^(\s*)import urllib3$", r"\1from pip._vendor import urllib3", text)
        path.write_text(text, encoding="utf-8")
    replace(
        vendor / "urllib3" / "response.py",
        "try:\n    try:\n        import brotlicffi as brotli  # type: ignore[import-not-found]\n"
        "    except ImportError:\n        import brotli  # type: ignore[import-not-found]\n"
        "except ImportError:\n    brotli = None",
        "brotli = None",
    )
    replace(
        vendor / "urllib3" / "util" / "request.py",
        "try:\n    try:\n        import brotlicffi as _unused_module_brotli  "
        "# type: ignore[import-not-found] # noqa: F401\n    except ImportError:\n"
        "        import brotli as _unused_module_brotli  "
        "# type: ignore[import-not-found] # noqa: F401\n"
        'except ImportError:\n    pass\nelse:\n    ACCEPT_ENCODING += ",br"',
        "",
    )
    replace(
        vendor / "urllib3" / "contrib" / "emscripten" / "__init__.py",
        "import urllib3.connection",
        "from pip._vendor.urllib3 import connection as urllib3_connection",
    )
    replace(
        vendor / "urllib3" / "contrib" / "emscripten" / "__init__.py",
        "urllib3.connection.",
        "urllib3_connection.",
        count=3,
    )
    replace(
        vendor / "urllib3" / "contrib" / "pyopenssl.py",
        "import urllib3.contrib.pyopenssl\n        urllib3.contrib.pyopenssl.inject_into_urllib3()",
        "from pip._vendor.urllib3.contrib import pyopenssl\n"
        "        pyopenssl.inject_into_urllib3()",
    )
    # CVE-2025-47273 affects setuptools.package_index, which pip does not vendor.
    # The scanner exception is valid only while this image has no full 70.3.0 copy.
    if (vendor / "setuptools").exists():
        raise RuntimeError("Recheck the setuptools scanner exception")
    try:
        setuptools_version = importlib.metadata.version("setuptools")
    except importlib.metadata.PackageNotFoundError:
        pass
    else:
        if setuptools_version == "70.3.0":
            raise RuntimeError("The full vulnerable setuptools package must not be installed")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
