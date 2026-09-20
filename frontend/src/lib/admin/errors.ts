type AdminErrorPayload = {
  code?: unknown;
  detail?: unknown;
  error?: unknown;
  message?: unknown;
  msg?: unknown;
};

type AdminTranslate = (key: string, vars?: Record<string, unknown>, fallback?: string) => string;

const ADMIN_ERROR_KEYS: Record<string, string> = {
  invalid_archive: "error_theme_archive",
  empty_archive: "error_theme_archive",
  zip_required: "error_theme_archive",
  archive_file_required: "error_theme_archive",
  one_archive_required: "error_theme_archive",
  invalid_theme_manifest: "error_theme_archive",
  invalid_theme_token: "error_theme_archive",
  invalid_json: "error_theme_archive",
  invalid_collection: "error_theme_archive",
  no_themes_found: "error_theme_archive",
  nested_theme_manifests: "error_theme_archive",
  duplicate_collection_path: "error_theme_archive",
  missing_css_file: "error_theme_archive",
  invalid_preview: "error_theme_archive",
  invalid_css: "error_theme_archive",
  missing_css_asset: "error_theme_archive",
  theme_alias_not_allowed: "error_theme_archive",
  theme_name_too_long: "error_theme_archive",
  invalid_export_selection: "error_theme_archive",
  import_failed: "error_theme_archive",
  css_too_deep: "error_theme_archive",
  catalog_changed: "error_theme_catalog_changed",
  catalog_reload_required: "error_theme_catalog_changed",
  managed_theme_removal_requires_library: "error_theme_catalog_changed",
  unsafe_path: "error_theme_unsafe",
  unsupported_zip_entry: "error_theme_unsafe",
  unsupported_theme_file: "error_theme_unsafe",
  unsafe_svg: "error_theme_unsafe",
  external_css_url: "error_theme_unsafe",
  css_import_not_allowed: "error_theme_unsafe",
  unsafe_css_property: "error_theme_unsafe",
  unsafe_css_function: "error_theme_unsafe",
  invalid_css_url: "error_theme_unsafe",
  url_in_theme_token: "error_theme_unsafe",
  archive_too_large: "error_theme_size",
  archive_limit: "error_theme_size",
  archive_too_deep: "error_theme_size",
  too_many_files: "error_theme_size",
  too_many_themes: "error_theme_size",
  theme_file_too_large: "error_theme_size",
  manifest_too_large: "error_theme_size",
  css_too_large: "error_theme_size",
  export_too_large: "error_theme_size",
  protected_theme: "error_theme_protected",
  active_theme: "error_theme_active",
  admin_theme_active: "error_theme_active",
  theme_exists: "error_theme_conflict",
  theme_requires_adoption: "error_theme_conflict",
  theme_not_managed: "error_theme_conflict",
  duplicate_theme_key: "error_theme_conflict",
  duplicate_path: "error_theme_conflict",
  idempotency_conflict: "error_theme_conflict",
  theme_modified_on_server: "error_theme_modified",
  import_changed: "error_theme_modified",
  package_corrupted: "error_theme_modified",
  incompatible_overrides: "error_theme_incompatible",
  incompatible_theme_api: "error_theme_incompatible",
  import_expired: "error_theme_import_expired",
  import_not_ready: "error_theme_import_expired",
  import_not_found: "error_theme_import_expired",
  import_interrupted: "error_theme_import_expired",
  import_already_installed: "error_theme_import_expired",
  too_many_imports: "error_theme_busy",
  themes_busy: "error_theme_busy",
  theme_storage_full: "error_theme_storage",
  insufficient_disk_space: "error_theme_storage",
  theme_storage_unavailable: "error_theme_storage",
  registry_invalid: "error_theme_storage",
  repository_unavailable: "error_theme_repository",
  repository_not_found: "error_theme_repository",
  repository_ref_not_found: "error_theme_repository",
  repository_ref_ambiguous: "error_theme_repository",
  repository_host_not_supported: "error_theme_repository",
  repository_address_blocked: "error_theme_repository",
  repository_url_not_supported: "error_theme_repository",
  subdirectory_not_found: "error_theme_repository",
  invalid_repository_url: "error_theme_repository",
  repository_rate_limited: "error_theme_rate_limit",
  no_previous_version: "error_theme_no_rollback",
  theme_preview_unavailable: "error_theme_preview",
  invalid_theme_selection: "error_theme_preview",
  admin_telegram_unavailable: "error_admin_telegram_unavailable",
  access_denied: "error_access_denied",
  backup_create_busy: "error_backup_busy",
  backup_restore_requires_maintenance: "error_backup_restore_requires_maintenance",
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
  invalid_audience: "error_invalid_audience",
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
  animated_image: "error_image_animated",
  empty_image: "error_image_invalid",
  image_dimensions: "error_image_dimensions",
  image_too_large: "error_image_too_large",
  invalid_image: "error_image_invalid",
  unsupported_image: "error_image_type",
  too_many_images: "error_image_count",
  payload_too_large: "error_image_too_large",
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

function errorPayload(value: unknown): AdminErrorPayload | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as AdminErrorPayload)
    : null;
}

function scalarErrorText(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function structuredErrorText(value: unknown): string {
  const scalar = scalarErrorText(value);
  if (scalar) return scalar;
  if (Array.isArray(value)) {
    return value.map(structuredErrorText).filter(Boolean).join("; ");
  }
  const payload = errorPayload(value);
  if (!payload) return "";
  return (
    scalarErrorText(payload.message) ||
    scalarErrorText(payload.msg) ||
    structuredErrorText(payload.detail)
  );
}

export function adminErrorMessage(result: unknown, at: AdminTranslate, fallback = ""): string {
  if (!result) return fallback || at("error", {}, "Error");

  const payload = errorPayload(result);
  const nestedError = errorPayload(payload?.error);
  const code =
    scalarErrorText(result) ||
    scalarErrorText(payload?.error) ||
    scalarErrorText(nestedError?.code) ||
    scalarErrorText(nestedError?.error) ||
    scalarErrorText(payload?.code);
  const rawMessage =
    typeof result === "string"
      ? ""
      : structuredErrorText(payload?.message) ||
        structuredErrorText(payload?.detail) ||
        structuredErrorText(nestedError?.message) ||
        structuredErrorText(nestedError?.detail);
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
