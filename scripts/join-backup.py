"""Reassemble and verify Telegram backup parts before normal ZIP restore."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from bot.services.backup_parts import BackupPartsError, join_backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Downloaded *.zip.parts.json manifest")
    parser.add_argument("--output", type=Path, help="Output ZIP path (must not exist)")
    args = parser.parse_args()
    try:
        result = join_backup(args.manifest, args.output)
    except (BackupPartsError, OSError) as exc:
        parser.exit(1, f"Cannot reassemble backup: {exc}\n")
    print(f"Verified backup ZIP: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
