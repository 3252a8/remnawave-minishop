from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APPEARANCE_SECTION = REPO_ROOT / "frontend/src/admin/sections/AppearanceSection.svelte"
APPEARANCE_BEHAVIOR_SETTINGS = (
    REPO_ROOT / "frontend/src/admin/sections/appearance/AppearanceBehaviorSettings.svelte"
)
APPEARANCE_BRAND_CARD = (
    REPO_ROOT / "frontend/src/admin/sections/appearance/AppearanceBrandCard.svelte"
)
APPEARANCE_DEFAULT_THEME_EDITOR = (
    REPO_ROOT / "frontend/src/admin/sections/appearance/AppearanceDefaultThemeEditor.svelte"
)
APPEARANCE_OPTIONS = REPO_ROOT / "frontend/src/lib/admin/appearanceOptions.ts"
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
    behavior = APPEARANCE_BEHAVIOR_SETTINGS.read_text(encoding="utf-8")

    assert '"WEBAPP_USER_THEME_MODE_ENABLED"' in source
    assert 'labelKey: "appearance_user_theme_mode_title"' in source
    assert "onChange: setUserThemeModeEnabled" in source
    assert '"WEBAPP_COMPACT_HOME_ENABLED"' in source
    assert '"settings_field_webapp_compact_home_enabled_label"' in source
    assert "onChange: setCompactHomeEnabled" in source
    assert '"WEBAPP_COMPACT_LOGIN_ENABLED"' in source
    assert '"settings_field_webapp_compact_login_enabled_label"' in source
    assert "onChange: setCompactLoginEnabled" in source
    assert '"WEBAPP_CHECKOUT_ADDON_VALUE_ANIMATION_ENABLED"' in source
    assert "onChange: setCheckoutAddonValueAnimationEnabled" in source
    assert '"WEBAPP_CHECKOUT_ADDON_EDITOR_EXPANDED_BY_DEFAULT"' in source
    assert "onChange: setCheckoutAddonEditorExpandedByDefault" in source
    assert "<AppearanceBehaviorSettings" in source
    assert "onCheckedChange={setting.onChange}" in behavior


def test_theme_editor_exposes_universal_home_element_visibility_controls():
    editor = APPEARANCE_DEFAULT_THEME_EDITOR.read_text(encoding="utf-8")
    options = APPEARANCE_OPTIONS.read_text(encoding="utf-8")

    assert "HOME_ELEMENT_VISIBILITY_FIELDS" in editor
    assert 'value: "auto"' in editor
    assert 'value: "visible"' in editor
    assert 'value: "hidden"' in editor
    for token in (
        "home_subscription_period_visibility",
        "home_tariff_name_visibility",
        "home_subscription_end_visibility",
        "home_regular_traffic_visibility",
        "home_premium_traffic_visibility",
        "home_change_tariff_visibility",
        "home_balance_visibility",
        "home_auto_renew_visibility",
    ):
        assert token in options
