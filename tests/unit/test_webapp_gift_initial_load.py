from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GIFT_FEATURE = REPO_ROOT / "frontend" / "src" / "webapp" / "gifts" / "GiftFeature.svelte"


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
