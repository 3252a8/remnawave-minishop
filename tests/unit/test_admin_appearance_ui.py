from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APPEARANCE_SECTION = REPO_ROOT / "frontend/src/admin/sections/AppearanceSection.svelte"
APPEARANCE_BRAND_CARD = (
    REPO_ROOT / "frontend/src/admin/sections/appearance/AppearanceBrandCard.svelte"
)
MOCK_ADMIN_FALLBACK = REPO_ROOT / "frontend/src/lib/webapp/mockApi/adminFallback.ts"


def test_appearance_upload_marks_unpersisted_assets_dirty():
    source = APPEARANCE_BRAND_CARD.read_text(encoding="utf-8")

    assert "function applyUploadedAppearanceField(" in source
    helper_start = source.index("function applyUploadedAppearanceField(")
    helper = source[helper_start : source.index("function handleLogoFileChange", helper_start)]

    assert "persisted === false" in helper
    assert "settingsStore.markDirty(key, value)" in helper
    assert "settingsStore.setFieldValue(key, value)" in helper
    assert "const persisted = uploaded?.persisted" in source
    assert 'applyUploadedAppearanceField("WEBAPP_FAVICON_URL", uploadedUrl, persisted)' in source
    assert 'applyUploadedAppearanceField("WEBAPP_FAVICON_USE_CUSTOM", true, persisted)' in source


def test_mock_favicon_upload_persists_custom_favicon_state():
    source = MOCK_ADMIN_FALLBACK.read_text(encoding="utf-8")
    route_start = source.index('if (path === "/admin/appearance/favicon")')
    route_block = source[route_start : source.index('if (path === "/admin/backups")', route_start)]

    assert "persistDemoSettings({" in route_block
    assert "WEBAPP_FAVICON_URL: faviconUrl" in route_block
    assert "WEBAPP_FAVICON_USE_CUSTOM: true" in route_block
    assert "persisted: true" in route_block


def test_appearance_exposes_user_theme_mode_toggle():
    source = APPEARANCE_SECTION.read_text(encoding="utf-8")

    assert '"WEBAPP_USER_THEME_MODE_ENABLED"' in source
    assert 'at("appearance_user_theme_mode_title"' in source
    assert "onCheckedChange={setUserThemeModeEnabled}" in source
