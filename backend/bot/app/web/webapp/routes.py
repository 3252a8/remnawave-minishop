# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405


def setup_subscription_webapp_routes(app: web.Application) -> None:
    app.router.add_get("/", index_route)
    app.router.add_get("/login/password", index_route)
    app.router.add_get("/home", index_route)
    app.router.add_get("/invite", index_route)
    app.router.add_get("/devices", index_route)
    app.router.add_get("/settings", index_route)
    app.router.add_get("/support", index_route)
    app.router.add_get("/support/{ticket_id:\\d+}", index_route)
    app.router.add_get("/admin", index_route)
    app.router.add_get(
        (
            "/admin/{section:stats|users|payments|promos|ads|broadcast|logs|tariffs|"
            "appearance|settings|support}"
        ),
        index_route,
    )
    app.router.add_get("/admin/users/{user_id:-?[0-9]+}", index_route)
    app.router.add_get("/admin/support/{ticket_id:\\d+}", index_route)
    app.router.add_get("/auth/telegram/start", telegram_oauth_start_route)
    app.router.add_get("/auth/telegram/callback", telegram_oauth_callback_route)
    app.router.add_get("/health", health_route)
    app.router.add_get(WEBAPP_LOGO_PROXY_PATH, webapp_logo_route)
    app.router.add_get(
        rf"{WEBAPP_UPLOADED_LOGO_PATH}/{{filename:[A-Za-z0-9_.-]+}}",
        webapp_uploaded_logo_route,
    )
    app.router.add_get(
        rf"{WEBAPP_FAVICON_PATH}/{{digest:[0-9a-f]{{16}}}}/{{filename:[A-Za-z0-9_.-]+}}",
        webapp_favicon_route,
    )
    app.router.add_get(
        r"/webapp-emoji/{codepoints:[0-9a-f_]+}/512.{ext:gif|webp}",
        webapp_animated_emoji_route,
    )
    app.router.add_get("/subscription_webapp.{asset_hash:[0-9a-f]{8}}.css", css_asset_route)
    app.router.add_get("/subscription_webapp.css", css_asset_route)
    app.router.add_get(r"/webapp-theme-css/{path:.+}", theme_css_asset_route)
    app.router.add_get(r"/webapp-theme-assets/{path:.+}", theme_asset_route)
    app.router.add_get("/subscription_webapp.min.{asset_hash}.js", js_asset_route)
    app.router.add_get("/subscription_webapp.js", js_asset_route)
    app.router.add_post("/api/auth/telegram/nonce", telegram_oauth_nonce_route)
    app.router.add_post("/api/auth/token", auth_token_route)
    app.router.add_post("/api/auth/email/request", email_auth_request_route)
    app.router.add_post("/api/auth/email/verify", email_auth_verify_route)
    app.router.add_post("/api/auth/email/magic", email_auth_magic_route)
    app.router.add_post("/api/auth/email/password", email_password_auth_route)
    app.router.add_post("/api/auth/logout", logout_route)
    app.router.add_get("/api/bootstrap", bootstrap_route)
    app.router.add_get("/api/i18n", i18n_route)
    app.router.add_get("/api/me", me_route)
    app.router.add_get("/api/account/avatar", account_avatar_route)
    app.router.add_post("/api/account/language", account_language_route)
    app.router.add_post("/api/account/email/request", account_email_request_route)
    app.router.add_post("/api/account/email/verify", account_email_verify_route)
    app.router.add_post("/api/account/password/request", account_password_request_route)
    app.router.add_post("/api/account/password/confirm", account_password_confirm_route)
    app.router.add_post("/api/account/telegram/link", account_telegram_link_route)
    app.router.add_post("/api/promo/apply", apply_promo_route)
    app.router.add_post("/api/trial/activate", activate_trial_route)
    app.router.add_get("/api/devices", devices_route)
    app.router.add_post("/api/devices/disconnect", disconnect_device_route)
    app.router.add_get("/api/devices/topup-options", device_topup_options_route)
    app.router.add_get("/api/support/tickets", support_tickets_route)
    app.router.add_post("/api/support/tickets", support_create_ticket_route)
    app.router.add_get("/api/support/tickets/{id:\\d+}", support_ticket_detail_route)
    app.router.add_post("/api/support/tickets/{id:\\d+}/messages", support_ticket_reply_route)
    app.router.add_post("/api/support/tickets/{id:\\d+}/read", support_ticket_read_route)
    app.router.add_get("/api/support/unread", support_unread_route)
    app.router.add_get("/api/tariffs/topup-options", tariff_topup_options_route)
    app.router.add_get("/api/tariffs/change-options", tariff_change_options_route)
    app.router.add_post("/api/tariffs/change", tariff_change_route)
    app.router.add_post("/api/tariffs/change-payment", tariff_change_payment_route)
    app.router.add_post("/api/payments", create_payment_route)
    app.router.add_get("/api/payments/{payment_id}", payment_status_route)
    setup_admin_routes(app)
