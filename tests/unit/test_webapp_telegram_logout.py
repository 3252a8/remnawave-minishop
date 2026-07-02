from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_telegram_init_data_login_runs_before_manual_logout_gate():
    source = _read("frontend/src/lib/webapp/webappBoot.ts")

    init_data_pos = source.index("const initData = getInitDataForBoot();")
    manual_logout_pos = source.index("if (isManuallyLoggedOut())")

    assert init_data_pos < manual_logout_pos


def test_logout_button_is_controlled_by_telegram_context():
    app_source = _read("frontend/src/App.svelte")
    shell_view_source = _read("frontend/src/lib/webapp/appShellView.ts")
    app_mode_source = _read("frontend/src/webapp/AppModeContent.svelte")
    authenticated_screens_source = _read("frontend/src/webapp/AuthenticatedScreens.svelte")
    settings_source = _read("frontend/src/webapp/screens/SettingsScreen.svelte")

    assert "const telegramMiniAppContext = hasTelegramLaunchParams();" in shell_view_source
    assert "{shellView}" in app_source
    assert "{telegramMiniAppContext}" in app_mode_source
    assert "showLogout={!telegramMiniAppContext}" in authenticated_screens_source
    assert "showLogout = true," in settings_source
    assert "{#if showLogout}" in settings_source


def test_shell_view_reactivity_keeps_dependencies_visible():
    app_source = _read("frontend/src/App.svelte")

    assert "computeCurrentShellView" not in app_source
    start = app_source.index("const shellView: AppShellView = $derived(")
    end = app_source.index("const telegramNotificationsNeedPrompt", start)
    shell_view_block = app_source[start:end]

    for dependency in (
        "authBusy,",
        "authStatus,",
        "data,",
        "screen,",
        "selectedTariffKey,",
        "telegramLoginBusy,",
        "telegramSdkStatus,",
        "tg,",
    ):
        assert dependency in shell_view_block


def test_logout_handler_is_noop_inside_telegram_mini_app():
    source = _read("frontend/src/lib/webapp/stores/accountStore.svelte.ts")

    guard_pos = source.index("if (telegramSdk.hasLaunchParams()) return;")
    mark_logout_pos = source.index("markManualLogout();")

    assert guard_pos < mark_logout_pos


def test_open_app_route_uses_fallback_screen_without_auth_flow():
    main_source = _read("frontend/src/main.ts")
    app_source = _read("frontend/src/App.svelte")
    app_mode_source = _read("frontend/src/webapp/AppModeContent.svelte")
    screen_source = _read("frontend/src/webapp/screens/AppLaunchScreen.svelte")

    assert "loadBootstrap().finally" in main_source
    assert "BOOTSTRAP_TIMEOUT_MS" in main_source
    assert "controller.abort()" in main_source
    assert "AppModeContent" in app_source
    assert "AppLaunchScreen" in app_mode_source
    assert 'mode: isAppLaunchRoute ? "appLaunch"' in app_source
    assert "window.close()" in screen_source
    assert 'window.addEventListener("blur", notePageLeft)' not in screen_source
    assert "CLOSE_ATTEMPT_DELAY_MS = 2500" in screen_source
    assert "if (pageLeft || document.hidden) tryCloseWindow();" in screen_source

    launch_guard_pos = app_source.index("if (isAppLaunchRoute) return;")
    boot_pos = app_source.index("boot();", launch_guard_pos)

    assert launch_guard_pos < boot_pos


def test_frontend_nginx_proxies_open_app_gateway_to_backend():
    source = _read("deploy/docker/frontend/nginx.conf")

    open_app_pos = source.index("location = /open-app")
    fallback_pos = source.index("location / {")
    block = source[open_app_pos:fallback_pos]

    assert open_app_pos < fallback_pos
    assert "proxy_pass http://backend:8081;" in block
