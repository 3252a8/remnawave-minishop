import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_SVELTE = REPO_ROOT / "frontend/src/App.svelte"
APP_SHELL_VIEW = REPO_ROOT / "frontend/src/lib/webapp/appShellView.ts"
WEBAPP_CSS = REPO_ROOT / "frontend/src/styles/webapp.css"
LOCALES = REPO_ROOT / "locales"


def test_sonner_toaster_uses_app_theme_and_unstyled_toasts():
    source = APP_SVELTE.read_text(encoding="utf-8")
    shell_view_source = APP_SHELL_VIEW.read_text(encoding="utf-8")

    assert "computeThemeView" in shell_view_source
    assert "themeView: {" in source
    assert "toastTheme" in source
    assert "theme={toastTheme}" in source
    assert "style={shellStyle}" in source
    assert 'toastOptions={{ class: "app-toast", unstyled: true }}' in source


def test_app_toast_class_owns_visual_surface():
    css = WEBAPP_CSS.read_text(encoding="utf-8")
    start = css.index(".app-toast {")
    end = css.index(".app-toast [data-content]", start)
    block = css[start:end]

    assert "background: color-mix(in srgb, var(--panel)" in block
    assert "color: var(--text);" in block
    assert "border: 1px solid var(--border-strong);" in block
    assert "box-shadow: var(--shadow-popover);" in block


def test_admin_traffic_grant_toast_locales_include_user_identity():
    for language in ("ru", "en"):
        messages = json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))
        for key in ("admin_traffic_grant_regular_done", "admin_traffic_grant_premium_done"):
            text = messages[key]
            assert "{gb}" in text
            assert "{user}" in text
            assert "{user_id}" in text
