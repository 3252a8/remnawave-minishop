from bot.app.web.admin_settings_manifest import manifest_payload


def test_telegram_bot_proxy_is_not_runtime_admin_setting() -> None:
    manifest_keys = {field["key"] for field in manifest_payload()}

    assert "TELEGRAM_BOT_PROXY_URL" not in manifest_keys
    assert "TELEGRAM_BOT_API_BASE_URL" not in manifest_keys
    assert "TELEGRAM_OAUTH_USE_BOT_PROXY" not in manifest_keys
