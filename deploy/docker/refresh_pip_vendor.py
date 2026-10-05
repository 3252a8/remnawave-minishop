"""Refresh pip's bundled libraries until an upstream release includes these fixes.

Keep pip's namespace/Brotli patches and pure-Python msgpack layout, as documented
at https://pip.pypa.io/en/stable/development/vendoring-policy/.
Remove this helper once upstream pip vendors urllib3 >= 2.8.0, msgpack >= 1.2.1,
and pkg_resources from setuptools >= 80.9.0 (or removes that legacy backend).
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
    for name, distribution, version, license_name in (
        ("urllib3", "urllib3", "2.8.0", "LICENSE.txt"),
        ("msgpack", "msgpack", "1.2.1", "COPYING"),
        ("pkg_resources", "setuptools", "80.9.0", "LICENSE"),
    ):
        shutil.rmtree(vendor / name)
        shutil.copytree(
            source / name,
            vendor / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.so", "*.pyd"),
        )
        shutil.copy2(
            source / f"{distribution}-{version}.dist-info" / "licenses" / license_name,
            vendor / name / license_name,
        )
        manifest = vendor / "vendor.txt"
        text = manifest.read_text(encoding="utf-8")
        text, count = re.subn(
            rf"(?m)^(\s*){distribution}==[^\n]+$",
            rf"\g<1>{distribution}=={version}",
            text,
        )
        if count != 1:
            raise RuntimeError(f"Expected one {name} entry in pip's vendor manifest")
        manifest.write_text(text, encoding="utf-8")

    # pip ships a CycloneDX inventory too; preserve it with accurate versions and
    # dependency references so SBOM consumers see the same libraries as Python.
    inventory = vendor / "bom.cdx.json"
    bom = json.loads(inventory.read_text(encoding="utf-8"))
    references: dict[str, str] = {}
    for name, version in (
        ("urllib3", "2.8.0"),
        ("msgpack", "1.2.1"),
        ("setuptools", "80.9.0"),
    ):
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
    resources = vendor / "pkg_resources" / "__init__.py"
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
