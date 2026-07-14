<script lang="ts">
  import { getHealthStore } from "$lib/admin/context";
  import { RefreshCw, TriangleAlert } from "$components/ui/icons.js";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import type { HealthAlert } from "../lib/admin/stores/healthStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    at = (key, _params = {}, fallback = "") => fallback || key,
    section = "stats",
    onNavigate = () => {},
  }: {
    at?: TranslateFn;
    section?: string;
    onNavigate?: (section: string) => void;
  } = $props();

  const healthStore = getHealthStore();

  const MESSAGE_FALLBACKS: Record<string, string> = {
    data_dir_missing:
      "Data directory ({path}) not found. Make sure the data volume is mounted into the container.",
    data_dir_not_writable:
      "No write access to {path} — backups, tariffs, logos and translations cannot be saved.",
    backups_dir_not_writable: "Backups directory {path} is not writable.",
    tariffs_config_invalid: "Tariffs file {path} cannot be read: {error}",
    locale_overrides_invalid: "Translations file {path} is corrupted: {error}",
    subscription_page_config_invalid: "Subscription guides config cannot be read: {error}",
    provider_not_configured:
      "Provider {provider} is enabled but not configured — payments through it will not work.",
    provider_webhook_needs_base_url:
      "Provider {provider} requires WEBHOOK_BASE_URL for webhooks, but it is not set.",
    no_payment_methods: "No payment method is enabled.",
    mini_app_url_missing:
      "SUBSCRIPTION_MINI_APP_URL is not set — the Mini App button will not appear in the bot.",
    mini_app_url_not_https: "SUBSCRIPTION_MINI_APP_URL must start with https:// (currently {url}).",
    redis_not_configured:
      "REDIS_URL is not set — bot dialog states and caches will not survive a restart.",
    smtp_incomplete: "SMTP is partially configured — email login will not work.",
    proxy_not_trusted:
      "Requests arrive through proxy {remote} which is not in TRUSTED_PROXIES — payment provider webhooks may be rejected by IP.",
    bot_token_invalid: "Telegram rejected BOT_TOKEN — the bot is not working.",
    telegram_api_error: "Failed to reach the Telegram API: {error}",
    telegram_webhook_missing: "Telegram webhook is not set — the bot does not receive updates.",
    telegram_webhook_mismatch: "Telegram webhook points to {actual}, expected {expected}.",
    telegram_webhook_error: "Telegram reports a webhook delivery error: {error}",
    telegram_webhook_pending: "{count} unprocessed updates are queued in Telegram.",
    panel_api_not_configured:
      "PANEL_API_URL and PANEL_API_KEY are not set — sync and subscription provisioning do not work.",
    panel_api_unreachable: "Remnawave panel is unreachable at {url}.",
  };

  const SECTION_FALLBACK_LABELS: Record<string, string> = {
    settings: "Settings",
    payments: "Payments",
    backups: "Backups",
    tariffs: "Tariffs",
    appearance: "Appearance",
    translations: "Translations",
    users: "Users",
  };

  function interpolate(template: string, params: Record<string, unknown> = {}): string {
    return String(template || "").replace(/\{(\w+)\}/g, (match, key) =>
      params[key] !== undefined && params[key] !== null ? String(params[key]) : match
    );
  }

  function alertText(alert: HealthAlert): string {
    const fallback = interpolate(
      MESSAGE_FALLBACKS[alert.message_key] || alert.message_key,
      alert.params
    );
    return at(`health_${alert.message_key}`, alert.params || {}, fallback);
  }

  function sectionLabel(id: string): string {
    return at(`nav_${id}`, {}, SECTION_FALLBACK_LABELS[id] || id);
  }

  const alerts = $derived(healthStore.alerts);
  const healthLoading = $derived(healthStore.healthLoading);
  const isDashboard = $derived(section === "stats");
  const visibleAlerts: HealthAlert[] = $derived(
    isDashboard ? alerts : alerts.filter((alert) => alert.sections.includes(section))
  );
  const errorCount = $derived(visibleAlerts.filter((alert) => alert.severity === "error").length);
</script>

{#if visibleAlerts.length}
  <div
    class="admin-config-alerts"
    class:admin-config-alerts-error={errorCount > 0}
    role="alert"
    aria-live="polite"
  >
    <div class="admin-config-alerts-head">
      <span class="admin-config-alerts-title">
        <TriangleAlert size={15} />
        {at("health_title", {}, "Configuration issues")}
      </span>
      {#if isDashboard}
        <AdminButton
          onclick={() => healthStore.loadHealth({ refresh: true })}
          disabled={healthLoading}
        >
          <RefreshCw size={13} />
          {at("health_refresh", {}, "Check again")}
        </AdminButton>
      {/if}
    </div>
    <ul class="admin-config-alerts-list">
      {#each visibleAlerts as alert (alert.id)}
        <li class="admin-config-alert admin-config-alert-{alert.severity}">
          <span class="admin-config-alert-dot" aria-hidden="true"></span>
          <span class="admin-config-alert-text">{alertText(alert)}</span>
          {#if isDashboard && (alert.sections || []).length}
            <span class="admin-config-alert-links">
              {#each alert.sections as sectionId (sectionId)}
                <button
                  type="button"
                  class="admin-config-alert-link"
                  onclick={() => onNavigate(sectionId)}
                >
                  {sectionLabel(sectionId)}
                </button>
              {/each}
            </span>
          {/if}
        </li>
      {/each}
    </ul>
  </div>
{/if}
