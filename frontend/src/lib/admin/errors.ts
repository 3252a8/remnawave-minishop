type AdminErrorPayload = {
  detail?: unknown;
  error?: unknown;
  message?: unknown;
};

type AdminTranslate = (key: string, vars?: Record<string, unknown>, fallback?: string) => string;

const ADMIN_ERROR_KEYS: Record<string, string> = {
  admin_telegram_unavailable: "error_admin_telegram_unavailable",
  access_denied: "error_access_denied",
  backup_create_busy: "error_backup_busy",
  backup_restore_busy: "error_backup_busy",
  backup_create_failed: "error_backup_create_failed",
  backup_list_failed: "error_backup_list_failed",
  backup_restore_failed: "error_backup_restore_failed",
  backup_upload_failed: "error_backup_upload_failed",
  bot_username_unavailable: "error_bot_username_unavailable",
  broadcast_schedule_future: "broadcast_schedule_future",
  button_kind_invalid: "error_invalid_payload",
  button_label_required: "error_button_label_required",
  button_label_too_long: "error_button_label_too_long",
  button_promo_code_invalid: "error_button_promo_code_invalid",
  button_promo_code_required: "error_button_promo_code_invalid",
  button_url_invalid: "error_button_url_invalid",
  button_url_required: "error_button_url_invalid",
  duplicate_code: "error_duplicate_code",
  email_not_configured: "error_email_not_configured",
  duplicate_start_param: "error_duplicate_start_param",
  empty_text: "error_empty_text",
  fulfillment_snapshot_invalid: "error_fulfillment_snapshot_invalid",
  fulfillment_snapshot_missing: "error_fulfillment_snapshot_missing",
  i18n_unavailable: "error_i18n_unavailable",
  invalid_amount: "error_invalid_amount",
  invalid_backup_archive: "error_invalid_backup_archive",
  invalid_bonus: "error_invalid_amount",
  invalid_deletes: "error_invalid_payload",
  invalid_days: "error_invalid_days",
  invalid_telegram_html: "broadcast_invalid_telegram_html",
  invalid_favicon: "error_invalid_favicon",
  invalid_kind: "error_invalid_payload",
  invalid_logo: "error_invalid_logo",
  invalid_payload: "error_invalid_payload",
  invalid_regular_bonus: "error_invalid_amount",
  invalid_tariffs_config: "error_invalid_tariffs_config",
  invalid_traffic_strategy: "error_invalid_traffic_strategy",
  invalid_updates: "error_invalid_payload",
  invalid_user_id: "error_invalid_payload",
  invalid_valid_days: "error_invalid_days",
  invalid_webapp_themes_config: "error_invalid_webapp_themes_config",
  missing_amount: "error_missing_amount",
  no_active_subscription: "error_no_active_subscription",
  no_panel_user: "error_no_panel_user",
  subscription_reissue_failed: "error_subscription_reissue_failed",
  no_changes: "error_no_changes",
  no_channels: "error_no_channels",
  no_telegram_account: "error_no_telegram_account",
  not_found: "error_not_found",
  promo_code_inactive: "error_promo_code_inactive",
  promo_code_not_found: "error_promo_code_not_found",
  panel_delete_failed: "error_panel_delete_failed",
  panel_update_failed: "error_panel_request_failed",
  panel_request_failed: "error_panel_request_failed",
  panel_service_unavailable: "error_panel_service_unavailable",
  panel_unavailable: "error_panel_service_unavailable",
  panel_user_missing: "error_panel_user_missing",
  payment_fulfillment_unavailable: "error_payment_fulfillment_unavailable",
  payment_manual_finalize_failed: "error_payment_manual_finalize_failed",
  payment_manual_finalize_unavailable: "error_payment_manual_finalize_unavailable",
  payment_reverse_conflict: "error_payment_reverse_conflict",
  payment_reversal_panel_failed: "error_payment_reversal_panel_failed",
  payment_reverse_unavailable: "error_payment_reverse_unavailable",
  payment_not_succeeded: "error_payment_not_succeeded",
  promo_conflict_confirmation_required: "error_promo_conflict_confirmation_required",
  preview_failed: "error_telegram_send_failed",
  queue_unavailable: "error_queue_unavailable",
  send_failed: "error_telegram_send_failed",
  subscription_service_unavailable: "error_subscription_service_unavailable",
  tariff_change_failed: "error_tariff_change_failed",
  tariff_required: "error_tariff_required",
  traffic_strategy_locked: "error_traffic_strategy_locked",
  too_many_buttons: "error_too_many_buttons",
  tribute_invalid_response: "error_tribute_request_failed",
  tribute_not_configured: "error_tribute_not_configured",
  tribute_rate_limited: "error_tribute_rate_limited",
  tribute_request_failed: "error_tribute_request_failed",
  tribute_unauthorized: "error_tribute_unauthorized",
  tribute_unavailable: "error_tribute_not_configured",
  unknown_shortcode: "broadcast_unknown_shortcode",
  webapp_url_unavailable: "error_webapp_url_unavailable",
  write_failed: "error_write_failed",
};

export function adminErrorMessage(result: unknown, at: AdminTranslate, fallback = ""): string {
  if (!result) return fallback || at("error", {}, "Error");

  const payload = typeof result === "object" ? (result as AdminErrorPayload) : null;
  const code = typeof result === "string" ? result : String(payload?.error || result || "");
  const rawMessage =
    typeof result === "string" ? "" : String(payload?.message || payload?.detail || "").trim();
  const key = ADMIN_ERROR_KEYS[code];

  if (key) {
    const base = at(key, {}, rawMessage || code || fallback || "Error");
    if (rawMessage && rawMessage !== code && rawMessage !== base) {
      return at(
        "error_with_details",
        { message: base, details: rawMessage },
        `${base}: ${rawMessage}`
      );
    }
    return base;
  }

  return rawMessage || code || fallback || at("error", {}, "Error");
}
