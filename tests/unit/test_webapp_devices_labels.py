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


def test_devices_screen_defers_unavailable_notice_until_the_limit_is_reached():
    source = (REPO_ROOT / "frontend/src/webapp/screens/DevicesScreen.svelte").read_text(
        encoding="utf-8"
    )

    assert "devicesLoaded && deviceLimitReached(devicesData, effectiveMaxDevices)" in source
    assert "subscription?.active && hasReachedDeviceLimit && deviceTopupUnavailableReason" in source
    assert 'deviceTopupUnavailableReason === "trial_subscription"' in source
    assert "onclick={openPaymentModal}" in source
