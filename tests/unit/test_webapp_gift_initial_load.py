from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GIFT_FEATURE = REPO_ROOT / "frontend" / "src" / "webapp" / "gifts" / "GiftFeature.svelte"
APP_MODE_CONTENT = REPO_ROOT / "frontend" / "src" / "webapp" / "AppModeContent.svelte"


def test_gift_list_refresh_does_not_wait_for_user_id() -> None:
    source = GIFT_FEATURE.read_text(encoding="utf-8")
    start = source.index("  $effect(() => {\n    const revision = giftState.revision;")
    end = source.index("  $effect(() => {", start + 1)
    refresh_effect = source[start:end]

    assert "if (loggedIn) {" in refresh_effect
    assert "userId" not in refresh_effect
    assert "void refreshGifts();" in refresh_effect


def test_incoming_gift_preview_does_not_wait_for_user_id() -> None:
    source = GIFT_FEATURE.read_text(encoding="utf-8")

    assert "if (loggedIn && giftState.token) {" in source
    assert "if (loggedIn && userId && giftState.token) {" not in source
    assert "void loadPreview(giftState.token);" in source


def test_incoming_gift_prompt_waits_for_preview() -> None:
    source = GIFT_FEATURE.read_text(encoding="utf-8")

    assert "{#if !claimBlocked && !error && (success || preview)}" in source


def test_successful_gift_activation_refreshes_and_opens_home() -> None:
    feature_source = GIFT_FEATURE.read_text(encoding="utf-8")
    claim_start = feature_source.index("  async function claim()")
    claim_end = feature_source.index("  async function copy", claim_start)
    claim = feature_source[claim_start:claim_end]

    assert "await onactivated();" in claim
    assert claim.index("await onactivated();") < claim.index("forgetGift();")
    assert claim.index("forgetGift();") < claim.index("giftState.open = false;")

    app_source = APP_MODE_CONTENT.read_text(encoding="utf-8")
    callback_start = app_source.index("    onactivated={async () => {")
    callback_end = app_source.index("    }}", callback_start)
    callback = app_source[callback_start:callback_end]

    assert "await stores.dataClient.loadData({ fresh: true });" in callback
    assert callback.index("await stores.dataClient.loadData") < callback.index("goHome();")


def test_gift_checkout_uses_configured_payment_method_display_mode() -> None:
    feature_source = GIFT_FEATURE.read_text(encoding="utf-8")
    app_source = APP_MODE_CONTENT.read_text(encoding="utf-8")

    gift_mount_start = app_source.index("  <GiftFeature")
    gift_mount_end = app_source.index("  />", gift_mount_start)
    assert "{paymentMethodsDisplayMode}" in app_source[gift_mount_start:gift_mount_end]

    checkout_start = feature_source.index("<PaymentCheckoutDialog")
    checkout_end = feature_source.index("/>", checkout_start)
    assert "{paymentMethodsDisplayMode}" in feature_source[checkout_start:checkout_end]
