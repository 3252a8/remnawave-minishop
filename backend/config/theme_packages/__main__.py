"""Author tooling: python -m config.theme_packages validate|inspect|pack|fork."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from .archive import deterministic_zip, extract_archive, inspect_collection
from .models import ExportRequest, PackageError
from .operations import export_themes
from .paths import atomic_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "inspect", "pack"):
        command = commands.add_parser(name)
        command.add_argument("source", type=Path)
        if name == "pack":
            command.add_argument("--output", type=Path, required=True)
        else:
            command.add_argument("--json", action="store_true")
    fork = commands.add_parser("fork")
    fork.add_argument("source", type=Path, help="Directory containing theme folders")
    fork.add_argument("key")
    fork.add_argument("--new-key", required=True)
    fork.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        with tempfile.TemporaryDirectory(prefix="minishop-themes-") as temp:
            root = Path(temp)
            if arguments.command == "fork":
                source = arguments.source.resolve()
                source_theme = source / arguments.key
                if not source_theme.resolve().is_relative_to(source):
                    raise PackageError("unsafe_path")
                shutil.copytree(source_theme, root / arguments.key)
                result = export_themes(
                    root,
                    ExportRequest(
                        keys=[arguments.key],
                        new_key=arguments.new_key,
                    ),
                )
                check = root / "_check"
                extract_archive(result, check)
                candidates = inspect_collection(check)
                if any(item.error for item in candidates):
                    raise PackageError(
                        "invalid_fork", "; ".join(item.detail for item in candidates)
                    )
                atomic_bytes(arguments.output, result)
                print(arguments.output)
                return 0
            source = arguments.source.resolve()
            if source.is_file():
                if source.stat().st_size > 20 * 1024 * 1024:
                    raise PackageError("archive_too_large")
                extract_archive(source.read_bytes(), root / "files")
                source = root / "files"
            candidates = inspect_collection(source)
            if arguments.command == "pack":
                if any(item.error for item in candidates):
                    raise PackageError(
                        "invalid_package", "; ".join(item.detail for item in candidates)
                    )
                output: dict[str, bytes] = {}
                for candidate in candidates:
                    folder = source / candidate.path
                    for file in folder.rglob("*"):
                        if file.is_file():
                            output[candidate.key + "/" + file.relative_to(folder).as_posix()] = (
                                file.read_bytes()
                            )
                output["minishop-themes.json"] = json.dumps(
                    {
                        "schema_version": 1,
                        "themes": [{"path": item.key} for item in candidates],
                    },
                    indent=2,
                ).encode()
                archive = deterministic_zip(output)
                if len(archive) > 20 * 1024 * 1024:
                    raise PackageError("archive_too_large")
                atomic_bytes(arguments.output, archive)
                print(arguments.output)
            elif arguments.json:
                print(
                    json.dumps(
                        [item.model_dump(mode="json") for item in candidates],
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                for candidate in candidates:
                    print(
                        f"{candidate.key or candidate.path}: {candidate.error or 'OK'} "
                        f"({candidate.files} files, {candidate.size} bytes) {candidate.detail}"
                    )
            return int(any(item.error for item in candidates))
    except (PackageError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
