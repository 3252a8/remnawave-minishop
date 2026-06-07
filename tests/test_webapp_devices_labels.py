import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_devices_labels_use_subscription_limit_before_devices_payload():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required to exercise the webapp label helpers")

    script = textwrap.dedent(
        """
        const mod = await import("./frontend/src/lib/webapp/devicesLabels.js");
        const t = (key, params = {}, fallback = "") => {
          if (key === "wa_devices_count") return `${params.current}/${params.max}`;
          if (key === "wa_devices_unlimited") return "Unlimited";
          return fallback || key;
        };
        const result = {
          missingLimit: mod.devicesLimitLabel(null, t),
          fallbackLimit: mod.devicesLimitLabel(null, t, 5),
          fallbackCount: mod.devicesCountLabel({ current_devices: 2 }, t, 5),
          fallbackPercent: mod.devicesPercent({ current_devices: 2 }, 5),
          unlimitedLimit: mod.devicesLimitLabel({ max_devices: 0 }, t),
          unlimitedPercent: mod.devicesPercent({ current_devices: 2, max_devices: 0 }),
        };
        console.log(JSON.stringify(result));
        """
    )

    completed = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload == {
        "missingLimit": "...",
        "fallbackLimit": "5",
        "fallbackCount": "2/5",
        "fallbackPercent": 40,
        "unlimitedLimit": "Unlimited",
        "unlimitedPercent": 100,
    }


def test_devices_screen_passes_subscription_limit_as_initial_fallback():
    source = (REPO_ROOT / "frontend/src/webapp/screens/DevicesScreen.svelte").read_text(
        encoding="utf-8"
    )

    assert "effectiveMaxDevices = devicesData?.max_devices ?? subscription?.max_devices" in source
    assert "devicesCountLabel(devicesData, t, effectiveMaxDevices)" in source
    assert "devicesPercent(devicesData, effectiveMaxDevices)" in source
    assert "devicesLimitLabel(devicesData, t, effectiveMaxDevices)" in source
