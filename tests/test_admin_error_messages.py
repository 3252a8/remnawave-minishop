import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ERRORS_JS = REPO_ROOT / "frontend" / "src" / "lib" / "admin" / "errors.js"


def test_admin_error_message_locale_keys_exist():
    source = ERRORS_JS.read_text(encoding="utf-8")
    keys = set(re.findall(r'"(error_[a-z0-9_]+)"', source))

    assert keys
    for language in ("ru", "en"):
        messages = json.loads(
            (REPO_ROOT / "locales" / f"{language}.json").read_text(encoding="utf-8")
        )
        missing = sorted(f"admin_{key}" for key in keys if f"admin_{key}" not in messages)
        assert missing == []
