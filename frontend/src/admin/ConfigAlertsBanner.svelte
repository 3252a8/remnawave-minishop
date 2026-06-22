<script lang="ts">
  import { getContext } from "svelte";
  import { RefreshCw, TriangleAlert } from "$components/ui/icons.js";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import type { HealthAlert, HealthStore } from "../lib/admin/stores/healthStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  export let at: TranslateFn = (key, _params = {}, fallback = "") => fallback || key;
  export let section = "stats";
  export let onNavigate: (section: string) => void = () => {};

  const healthStore = getContext<HealthStore>("healthStore");

  const MESSAGE_FALLBACKS: Record<string, string> = {
    data_dir_missing:
      "Каталог data ({path}) не найден. Проверьте, что том data смонтирован в контейнер.",
    data_dir_not_writable:
      "Нет прав на запись в {path} — бэкапы, тарифы, логотипы и переводы не сохранятся.",
    backups_dir_not_writable: "Каталог бэкапов {path} недоступен для записи.",
    tariffs_config_invalid: "Файл тарифов {path} не читается: {error}",
    locale_overrides_invalid: "Файл переводов {path} повреждён: {error}",
    subscription_page_config_invalid: "Конфиг гайдов подписки не читается: {error}",
    provider_not_configured:
      "Провайдер {provider} включён, но не настроен — оплата через него не работает.",
    provider_webhook_needs_base_url:
      "Провайдеру {provider} нужен WEBHOOK_BASE_URL для приёма вебхуков, а он не задан.",
    no_payment_methods: "Не включён ни один способ оплаты.",
    mini_app_url_missing:
      "SUBSCRIPTION_MINI_APP_URL не задан — кнопка Mini App в боте не появится.",
    mini_app_url_not_https:
      "SUBSCRIPTION_MINI_APP_URL должен начинаться с https:// (сейчас {url}).",
    redis_not_configured:
      "REDIS_URL не задан — состояния диалогов бота и кэш не переживут перезапуск.",
    smtp_incomplete: "SMTP настроен не полностью — вход по email работать не будет.",
    proxy_not_trusted:
      "Запросы приходят через прокси {remote}, которого нет в TRUSTED_PROXIES — вебхуки платёжных провайдеров могут отклоняться по IP.",
    bot_token_invalid: "Telegram отверг BOT_TOKEN — бот не работает.",
    telegram_api_error: "Не удалось обратиться к Telegram API: {error}",
    telegram_webhook_missing: "Вебхук Telegram не установлен — бот не получает обновления.",
    telegram_webhook_mismatch: "Вебхук Telegram указывает на {actual}, ожидается {expected}.",
    telegram_webhook_error: "Telegram сообщает об ошибке доставки вебхука: {error}",
    telegram_webhook_pending: "В очереди Telegram скопилось {count} необработанных обновлений.",
    panel_api_not_configured:
      "PANEL_API_URL и PANEL_API_KEY не заданы — синхронизация и выдача подписок не работают.",
    panel_api_unreachable: "Панель Remnawave недоступна по адресу {url}.",
  };

  const SECTION_FALLBACK_LABELS: Record<string, string> = {
    settings: "Настройки",
    payments: "Платежи",
    backups: "Бэкапы",
    tariffs: "Тарифы",
    appearance: "Внешний вид",
    translations: "Переводы",
    users: "Пользователи",
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

  $: alerts = $healthStore.alerts;
  $: healthLoading = $healthStore.healthLoading;
  $: isDashboard = section === "stats";
  $: visibleAlerts = (
    isDashboard ? alerts : alerts.filter((alert) => alert.sections.includes(section))
  ) as HealthAlert[];
  $: errorCount = visibleAlerts.filter((alert) => alert.severity === "error").length;
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
        {at("health_title", {}, "Проблемы конфигурации")}
      </span>
      {#if isDashboard}
        <AdminButton
          onclick={() => healthStore.loadHealth({ refresh: true })}
          disabled={healthLoading}
        >
          <RefreshCw size={13} />
          {at("health_refresh", {}, "Проверить снова")}
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
                  on:click={() => onNavigate(sectionId)}
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
