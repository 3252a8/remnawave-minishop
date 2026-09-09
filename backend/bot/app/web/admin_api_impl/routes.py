from aiohttp import web

from .ads import (
    admin_ad_create_route,
    admin_ad_delete_route,
    admin_ad_toggle_route,
    admin_ads_list_route,
)
from .backups import (
    admin_backups_create_route,
    admin_backups_list_route,
    admin_backups_restore_route,
    admin_backups_upload_route,
)
from .broadcast import (
    admin_broadcast_audience_counts_route,
    admin_broadcast_delete_route,
    admin_broadcast_reschedule_route,
    admin_broadcast_route,
    admin_broadcasts_list_route,
)
from .broadcast_shortcodes import (
    admin_broadcast_preview_route,
    admin_broadcast_shortcodes_route,
)
from .gift_creation import (
    admin_gift_create_route,
    admin_gift_detail_route,
    admin_gift_options_route,
)
from .gifts import admin_gift_revoke_route, admin_gifts_route
from .health import (
    admin_health_route,
)
from .logs import (
    admin_logs_route,
)
from .panel import (
    admin_panel_internal_squads_route,
)
from .partners import (
    admin_partner_application_approve_route,
    admin_partner_application_detail_route,
    admin_partner_application_reject_route,
    admin_partner_application_reopen_route,
    admin_partner_applications_route,
    admin_partner_attention_route,
    admin_partner_balance_adjustment_route,
    admin_partner_bulk_referral_import_preview_route,
    admin_partner_bulk_referral_import_route,
    admin_partner_close_route,
    admin_partner_create_route,
    admin_partner_detail_route,
    admin_partner_link_rotate_route,
    admin_partner_overview_route,
    admin_partner_pause_route,
    admin_partner_rate_route,
    admin_partner_referral_import_preview_route,
    admin_partner_referral_import_route,
    admin_partner_resume_route,
    admin_partner_withdrawal_detail_route,
    admin_partner_withdrawal_fail_route,
    admin_partner_withdrawal_paid_route,
    admin_partner_withdrawal_processing_route,
    admin_partner_withdrawal_reject_route,
    admin_partner_withdrawal_reveal_route,
    admin_partner_withdrawals_route,
    admin_partners_list_route,
)
from .payments import (
    admin_payment_detail_route,
    admin_payment_finalize_route,
    admin_payment_reverse_route,
    admin_payments_export_route,
    admin_payments_list_route,
)
from .promos import (
    admin_promo_activations_route,
    admin_promo_create_route,
    admin_promo_delete_route,
    admin_promo_detail_route,
    admin_promo_options_route,
    admin_promo_update_route,
    admin_promos_list_route,
)
from .settings import (
    admin_settings_get_route,
    admin_settings_patch_route,
)
from .stats import (
    admin_me_route,
    admin_stats_route,
)
from .support import (
    admin_message_image_route,
    admin_support_stats_route,
    admin_support_ticket_detail_route,
    admin_support_ticket_patch_route,
    admin_support_ticket_read_route,
    admin_support_ticket_reply_route,
    admin_support_ticket_typing_route,
    admin_support_tickets_route,
)
from .sync import (
    admin_sync_route,
)
from .tariffs import (
    admin_tariff_reconciliation_apply_route,
    admin_tariff_reconciliation_get_route,
    admin_tariffs_get_route,
    admin_tariffs_save_route,
)
from .tariffs_tribute import (
    admin_tariffs_tribute_catalog_route,
)
from .themes import (
    admin_appearance_favicon_upload_route,
    admin_appearance_logo_upload_route,
    admin_themes_get_route,
    admin_themes_save_route,
)
from .translations import (
    admin_translations_get_route,
    admin_translations_patch_route,
)
from .users import (
    admin_user_avatar_route,
    admin_user_balance_adjustment_route,
    admin_user_balance_conversion_route,
    admin_user_ban_route,
    admin_user_delete_route,
    admin_user_detail_route,
    admin_user_extend_route,
    admin_user_hwid_device_limit_route,
    admin_user_message_preview_route,
    admin_user_message_route,
    admin_user_notification_preferences_route,
    admin_user_premium_override_route,
    admin_user_referrals_route,
    admin_user_regular_traffic_override_route,
    admin_user_reset_trial_route,
    admin_user_squad_overrides_refresh_route,
    admin_user_squad_overrides_route,
    admin_user_subscription_reissue_route,
    admin_user_tariff_route,
    admin_user_telegram_profile_link_route,
    admin_user_traffic_grant_route,
    admin_user_traffic_strategy_route,
    admin_users_list_route,
)


def setup_admin_routes(app: web.Application) -> None:
    from .theme_library import setup_theme_jobs, setup_theme_library

    setup_theme_jobs(app)
    setup_theme_library(app.router)
    router = app.router
    router.add_get("/api/admin/me", admin_me_route)
    router.add_get("/api/admin/stats", admin_stats_route)
    router.add_get("/api/admin/health", admin_health_route)

    router.add_get("/api/admin/partners/attention", admin_partner_attention_route)
    router.add_get("/api/admin/partners/overview", admin_partner_overview_route)
    router.add_get("/api/admin/partners", admin_partners_list_route)
    router.add_post("/api/admin/partners", admin_partner_create_route)
    router.add_get(
        "/api/admin/partners/referral-import",
        admin_partner_bulk_referral_import_preview_route,
    )
    router.add_post(
        "/api/admin/partners/referral-import",
        admin_partner_bulk_referral_import_route,
    )
    router.add_get("/api/admin/partners/{id:\\d+}", admin_partner_detail_route)
    router.add_get(
        "/api/admin/partners/{id:\\d+}/referral-import",
        admin_partner_referral_import_preview_route,
    )
    router.add_post(
        "/api/admin/partners/{id:\\d+}/referral-import",
        admin_partner_referral_import_route,
    )
    router.add_post(
        "/api/admin/partners/{id:\\d+}/commission-rate",
        admin_partner_rate_route,
    )
    router.add_post(
        "/api/admin/partners/{id:\\d+}/balance-adjustments",
        admin_partner_balance_adjustment_route,
    )
    router.add_post("/api/admin/partners/{id:\\d+}/pause", admin_partner_pause_route)
    router.add_post("/api/admin/partners/{id:\\d+}/resume", admin_partner_resume_route)
    router.add_post("/api/admin/partners/{id:\\d+}/close", admin_partner_close_route)
    router.add_post(
        "/api/admin/partners/{id:\\d+}/link/rotate",
        admin_partner_link_rotate_route,
    )
    router.add_get("/api/admin/partner-applications", admin_partner_applications_route)
    router.add_get(
        "/api/admin/partner-applications/{id:\\d+}",
        admin_partner_application_detail_route,
    )
    router.add_post(
        "/api/admin/partner-applications/{id:\\d+}/approve",
        admin_partner_application_approve_route,
    )
    router.add_post(
        "/api/admin/partner-applications/{id:\\d+}/reject",
        admin_partner_application_reject_route,
    )
    router.add_post(
        "/api/admin/partner-applications/{id:\\d+}/reopen",
        admin_partner_application_reopen_route,
    )
    router.add_get("/api/admin/partner-withdrawals", admin_partner_withdrawals_route)
    router.add_get(
        "/api/admin/partner-withdrawals/{id:\\d+}",
        admin_partner_withdrawal_detail_route,
    )
    router.add_post(
        "/api/admin/partner-withdrawals/{id:\\d+}/reveal",
        admin_partner_withdrawal_reveal_route,
    )
    router.add_post(
        "/api/admin/partner-withdrawals/{id:\\d+}/processing",
        admin_partner_withdrawal_processing_route,
    )
    router.add_post(
        "/api/admin/partner-withdrawals/{id:\\d+}/paid",
        admin_partner_withdrawal_paid_route,
    )
    router.add_post(
        "/api/admin/partner-withdrawals/{id:\\d+}/reject",
        admin_partner_withdrawal_reject_route,
    )
    router.add_post(
        "/api/admin/partner-withdrawals/{id:\\d+}/fail",
        admin_partner_withdrawal_fail_route,
    )

    router.add_get("/api/admin/users", admin_users_list_route)
    router.add_get("/api/admin/users/{user_id:-?\\d+}", admin_user_detail_route)
    router.add_get("/api/admin/users/{user_id:-?\\d+}/referrals", admin_user_referrals_route)
    router.add_get("/api/admin/users/{user_id:-?\\d+}/avatar", admin_user_avatar_route)
    router.add_post("/api/admin/users/{user_id:-?\\d+}/ban", admin_user_ban_route)
    router.add_post(
        "/api/admin/users/{user_id:-?\\d+}/balance-adjustment",
        admin_user_balance_adjustment_route,
    )
    router.add_post(
        "/api/admin/users/{user_id:-?\\d+}/balance-conversion",
        admin_user_balance_conversion_route,
    )
    router.add_post("/api/admin/users/{user_id:-?\\d+}/message", admin_user_message_route)
    router.add_patch(
        "/api/admin/users/{user_id:-?\\d+}/notification-preferences",
        admin_user_notification_preferences_route,
    )
    router.add_post(
        "/api/admin/users/{user_id:-?\\d+}/message/preview", admin_user_message_preview_route
    )
    router.add_post(
        "/api/admin/users/{user_id:-?\\d+}/telegram-profile-link",
        admin_user_telegram_profile_link_route,
    )
    router.add_get("/api/admin/gifts", admin_gifts_route)
    router.add_get("/api/admin/gifts/options", admin_gift_options_route)
    router.add_post("/api/admin/gifts", admin_gift_create_route)
    router.add_get("/api/admin/gifts/{gift_id}", admin_gift_detail_route)
    router.add_post("/api/admin/users/{user_id:-?\\d+}/reset-trial", admin_user_reset_trial_route)
    router.add_post(
        "/api/admin/users/{user_id:-?\\d+}/subscription-reissue",
        admin_user_subscription_reissue_route,
    )
    router.add_patch(
        "/api/admin/users/{user_id:-?\\d+}/squad-overrides",
        admin_user_squad_overrides_route,
    )
    router.add_post(
        "/api/admin/users/{user_id:-?\\d+}/squad-overrides/refresh",
        admin_user_squad_overrides_refresh_route,
    )
    router.add_post("/api/admin/users/{user_id:-?\\d+}/extend", admin_user_extend_route)
    router.add_post("/api/admin/users/{user_id:-?\\d+}/tariff", admin_user_tariff_route)
    router.add_post(
        "/api/admin/users/{user_id:-?\\d+}/premium-override",
        admin_user_premium_override_route,
    )
    router.add_post(
        "/api/admin/users/{user_id:-?\\d+}/regular-traffic-override",
        admin_user_regular_traffic_override_route,
    )
    router.add_post(
        "/api/admin/users/{user_id:-?\\d+}/traffic-strategy",
        admin_user_traffic_strategy_route,
    )
    router.add_post(
        "/api/admin/users/{user_id:-?\\d+}/hwid-device-limit",
        admin_user_hwid_device_limit_route,
    )
    router.add_post(
        "/api/admin/users/{user_id:-?\\d+}/traffic-grant",
        admin_user_traffic_grant_route,
    )
    router.add_delete("/api/admin/users/{user_id:-?\\d+}", admin_user_delete_route)

    router.add_get("/api/admin/payments", admin_payments_list_route)
    router.add_get("/api/admin/payments/{payment_id:\\d+}", admin_payment_detail_route)
    router.add_post("/api/admin/payments/{payment_id:\\d+}/finalize", admin_payment_finalize_route)
    router.add_post("/api/admin/payments/{payment_id:\\d+}/reverse", admin_payment_reverse_route)
    router.add_get("/api/admin/payments/export.csv", admin_payments_export_route)

    router.add_post("/api/admin/gifts/{gift_id:\\d+}/revoke", admin_gift_revoke_route)

    router.add_get("/api/admin/promos", admin_promos_list_route)
    router.add_post("/api/admin/promos", admin_promo_create_route)
    router.add_get("/api/admin/promos/options", admin_promo_options_route)
    router.add_get("/api/admin/promos/{promo_id:\\d+}", admin_promo_detail_route)
    router.add_get("/api/admin/promos/{promo_id:\\d+}/activations", admin_promo_activations_route)
    router.add_patch("/api/admin/promos/{promo_id:\\d+}", admin_promo_update_route)
    router.add_delete("/api/admin/promos/{promo_id:\\d+}", admin_promo_delete_route)

    router.add_get("/api/admin/logs", admin_logs_route)

    router.add_get("/api/admin/support/tickets", admin_support_tickets_route)
    router.add_get("/api/admin/support/tickets/{id:\\d+}", admin_support_ticket_detail_route)
    router.add_post(
        "/api/admin/support/tickets/{id:\\d+}/messages",
        admin_support_ticket_reply_route,
    )
    router.add_patch("/api/admin/support/tickets/{id:\\d+}", admin_support_ticket_patch_route)
    router.add_post("/api/admin/support/tickets/{id:\\d+}/read", admin_support_ticket_read_route)
    router.add_post(
        "/api/admin/support/tickets/{id:\\d+}/typing",
        admin_support_ticket_typing_route,
    )
    router.add_get("/api/admin/support/stats", admin_support_stats_route)
    router.add_get(
        r"/api/admin/message-images/{image_id:[0-9a-f]{32}}",
        admin_message_image_route,
    )

    router.add_get("/api/admin/broadcast/audience-counts", admin_broadcast_audience_counts_route)
    router.add_get("/api/admin/broadcast/shortcodes", admin_broadcast_shortcodes_route)
    router.add_post("/api/admin/broadcast/preview", admin_broadcast_preview_route)
    router.add_post("/api/admin/broadcast", admin_broadcast_route)
    router.add_get("/api/admin/broadcasts", admin_broadcasts_list_route)
    router.add_patch("/api/admin/broadcasts/{id:\\d+}", admin_broadcast_reschedule_route)
    router.add_delete("/api/admin/broadcasts/{id:\\d+}", admin_broadcast_delete_route)
    router.add_post("/api/admin/sync", admin_sync_route)

    router.add_get("/api/admin/ads", admin_ads_list_route)
    router.add_post("/api/admin/ads", admin_ad_create_route)
    router.add_post("/api/admin/ads/{campaign_id:\\d+}/toggle", admin_ad_toggle_route)
    router.add_delete("/api/admin/ads/{campaign_id:\\d+}", admin_ad_delete_route)

    router.add_get("/api/admin/settings", admin_settings_get_route)
    router.add_patch("/api/admin/settings", admin_settings_patch_route)
    router.add_get("/api/admin/translations", admin_translations_get_route)
    router.add_patch("/api/admin/translations", admin_translations_patch_route)

    router.add_get("/api/admin/tariffs", admin_tariffs_get_route)
    router.add_put("/api/admin/tariffs", admin_tariffs_save_route)
    router.add_get(
        "/api/admin/tariffs/reconciliation",
        admin_tariff_reconciliation_get_route,
    )
    router.add_post(
        "/api/admin/tariffs/reconciliation",
        admin_tariff_reconciliation_apply_route,
    )
    router.add_get("/api/admin/tariffs/tribute/catalog", admin_tariffs_tribute_catalog_route)
    router.add_get("/api/admin/themes", admin_themes_get_route)
    router.add_put("/api/admin/themes", admin_themes_save_route)
    router.add_post("/api/admin/appearance/logo", admin_appearance_logo_upload_route)
    router.add_post("/api/admin/appearance/favicon", admin_appearance_favicon_upload_route)
    router.add_get("/api/admin/backups", admin_backups_list_route)
    router.add_post("/api/admin/backups/create", admin_backups_create_route)
    router.add_post("/api/admin/backups/upload", admin_backups_upload_route)
    router.add_post("/api/admin/backups/restore", admin_backups_restore_route)
    router.add_get("/api/admin/panel/internal-squads", admin_panel_internal_squads_route)
