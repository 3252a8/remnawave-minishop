from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_devices_screen_passes_subscription_limit_as_initial_fallback():
    source = (REPO_ROOT / "frontend/src/webapp/screens/DevicesScreen.svelte").read_text(
        encoding="utf-8"
    )

    assert (
        "effectiveMaxDevices = $derived(devicesData?.max_devices ?? subscription?.max_devices)"
        in source
    )
    assert "devicesCountLabel(devicesData, t, effectiveMaxDevices)" in source
    assert "devicesPercent(devicesData, effectiveMaxDevices)" in source
    assert "devicesLimitLabel(devicesData, t, effectiveMaxDevices)" in source
