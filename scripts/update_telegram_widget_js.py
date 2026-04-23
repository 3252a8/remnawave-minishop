from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.request import Request, urlopen


SOURCE_URL = "https://telegram.org/js/telegram-widget.js?23"
TARGET_PATH = (
    Path(__file__).resolve().parents[1]
    / "bot"
    / "app"
    / "web"
    / "templates"
    / "telegram-widget.js"
)
_UNPATCHED_WIDGET_ORIGIN_SNIPPET = """    if (origin == 'https://telegram.org') {\n      origin = default_origin;\n    } else if (origin == 'https://telegram-js.azureedge.net' || origin == 'https://tg.dev') {\n      origin = dev_origin;\n    }\n"""
_PATCHED_WIDGET_ORIGIN_SNIPPET = """    if (origin == 'https://telegram.org') {\n      origin = default_origin;\n    } else if (origin == 'https://telegram-js.azureedge.net' || origin == 'https://tg.dev') {\n      origin = dev_origin;\n    } else {\n      origin = default_origin;\n    }\n"""


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


def _normalize_widget_sdk(data: bytes) -> bytes:
    # Keep the vendored widget pointing to Telegram's OAuth host instead of the local origin.
    text = data.decode("utf-8")
    normalized = text.replace(
        _UNPATCHED_WIDGET_ORIGIN_SNIPPET,
        _PATCHED_WIDGET_ORIGIN_SNIPPET,
        1,
    )
    return normalized.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download the latest Telegram Login Widget SDK into the local templates directory."
    )
    parser.add_argument(
        "--source-url",
        default=SOURCE_URL,
        help="Telegram Login Widget SDK URL to download from.",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=TARGET_PATH,
        help="Output path for the vendored SDK.",
    )
    args = parser.parse_args()

    data = _normalize_widget_sdk(_download(args.source_url))
    args.target.parent.mkdir(parents=True, exist_ok=True)
    args.target.write_bytes(data)
    print(f"Wrote {len(data)} bytes to {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
