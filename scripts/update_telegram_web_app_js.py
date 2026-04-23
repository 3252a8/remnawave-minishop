from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.request import Request, urlopen


SOURCE_URL = "https://telegram.org/js/telegram-web-app.js"
TARGET_PATH = (
    Path(__file__).resolve().parents[1]
    / "bot"
    / "app"
    / "web"
    / "templates"
    / "telegram-web-app.js"
)


def _download(source_url: str) -> bytes:
    request = Request(
        source_url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/javascript,text/javascript,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download the latest Telegram Web App SDK into the local templates directory."
    )
    parser.add_argument(
        "--source-url",
        default=SOURCE_URL,
        help="Telegram Web App SDK URL to download from.",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=TARGET_PATH,
        help="Output path for the vendored SDK.",
    )
    args = parser.parse_args()

    data = _download(args.source_url)
    args.target.parent.mkdir(parents=True, exist_ok=True)
    args.target.write_bytes(data)
    print(f"Wrote {len(data)} bytes to {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
