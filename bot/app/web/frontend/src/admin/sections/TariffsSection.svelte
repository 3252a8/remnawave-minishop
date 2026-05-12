<script>
  import { RefreshCw, Trash2, Plus } from "$components/ui/icons.js";
  import { getContext, onMount } from "svelte";
  import { AdminBadge, AdminButton, AdminEmptyState } from "$components/patterns/admin/index.js";

  export let at;
  export let fmtMoney;

  const tariffsStore = getContext("tariffsStore");

  $: ({
    tariffsCatalog,
    tariffsLoading,
    tariffsPath,
    tariffsSaving,
  } = $tariffsStore);

  $: enabledTariffs = (tariffsCatalog.tariffs || []).filter((tariff) => tariff.enabled !== false);
  $: disabledTariffs = Math.max(0, (tariffsCatalog.tariffs || []).length - enabledTariffs.length);

  function tariffName(tariff) {
    return tariff?.names?.ru || tariff?.names?.en || tariff?.key || "—";
  }

  function tariffPriceSummary(tariff) {
    if (tariff.billing_model === "traffic") {
      const rub = tariff.traffic_packages?.rub || [];
      const first = rub[0];
      return first ? `${first.gb} GB ${at("at", {}, "за")} ${fmtMoney(first.price, "RUB")}` : at("tariff_traffic_packages", {}, "Пакеты трафика");
    }
    const months = [...(tariff.enabled_periods || [])].sort((a, b) => a - b);
    return months
      .map((month) => {
        const rub = tariff.prices_rub?.[String(month)];
        const stars = tariff.prices_stars?.[String(month)];
        if (rub) return `${month} ${at("months_short", {}, "мес.")} ${fmtMoney(rub, "RUB")}`;
        if (stars) return `${month} ${at("months_short", {}, "мес.")} ${stars} ⭐`;
        return `${month} ${at("months_short", {}, "мес.")}`;
      })
      .join(" · ");
  }

  onMount(() => {
    tariffsStore.loadTariffs();
  });
</script>

{#if tariffsLoading}
  <AdminEmptyState>{at("loading", {}, "Загрузка…")}</AdminEmptyState>
{:else}
  <div class="admin-stat-grid">
    <div class="admin-stat-card">
      <span class="admin-stat-label">{at("tariffs_stat_total", {}, "Всего тарифов")}</span>
      <strong class="admin-stat-value">{tariffsCatalog.tariffs.length}</strong>
      <span class="admin-stat-trend">{at("tariffs_stat_enabled", {}, "Включено")}: {enabledTariffs.length}</span>
    </div>
    <div class="admin-stat-card">
      <span class="admin-stat-label">{at("tariffs_stat_default", {}, "По умолчанию")}</span>
      <strong class="admin-stat-value">{tariffsCatalog.default_tariff || "—"}</strong>
      <span class="admin-stat-trend">{at("tariffs_stat_default_hint", {}, "Используется для новых подписок")}</span>
    </div>
    <div class="admin-stat-card">
      <span class="admin-stat-label">{at("tariffs_stat_disabled", {}, "Отключено")}</span>
      <strong class="admin-stat-value">{disabledTariffs}</strong>
      <span class="admin-stat-trend">{at("tariffs_stat_disabled_hint", {}, "Скрыто с витрины")}</span>
    </div>
  </div>

  <article class="admin-card">
    <header class="admin-card-head">
      <div>
        <h3>{at("tariffs_title", {}, "Каталог тарифов")}</h3>
        <small>{tariffsPath || "data/tariffs.json"}</small>
      </div>
      <div class="admin-editor-section-actions">
        <AdminButton size="sm" onclick={tariffsStore.loadTariffs} disabled={tariffsLoading || tariffsSaving}>
          <RefreshCw size={13} /> {at("btn_refresh", {}, "Обновить")}
        </AdminButton>
        <AdminButton size="sm" variant="primary" onclick={tariffsStore.openCreateTariff} disabled={tariffsLoading || tariffsSaving}>
          <Plus size={13} /> {at("btn_create_tariff", {}, "Создать тариф")}
        </AdminButton>
      </div>
    </header>
    <div class="admin-card-body">
      {#if !tariffsCatalog.tariffs.length}
        <AdminEmptyState>
          {at("tariffs_catalog_empty", {}, "Каталог пуст. Добавьте первый тариф, после сохранения будет создан JSON-файл каталога.")}
        </AdminEmptyState>
      {:else}
        <div class="admin-tariff-grid">
          {#each tariffsCatalog.tariffs as tariff}
            <article class="admin-tariff-card" class:is-disabled={tariff.enabled === false}>
              <div class="admin-tariff-top">
                <div>
                  <div class="admin-tariff-title">
                    <strong>{tariffName(tariff)}</strong>
                    {#if tariff.key === tariffsCatalog.default_tariff}
                      <AdminBadge variant="success">{at("status_default", {}, "Default")}</AdminBadge>
                    {/if}
                  </div>
                  <code>{tariff.key}</code>
                </div>
                {#if tariff.enabled === false}
                  <AdminBadge variant="muted">{at("status_disabled", {}, "Выключен")}</AdminBadge>
                {:else}
                  <AdminBadge variant="success">{at("status_active", {}, "Активен")}</AdminBadge>
                {/if}
              </div>
              <p>{tariff.descriptions?.ru || tariff.descriptions?.en || at("no_description", {}, "Без описания")}</p>
              <div class="admin-tariff-facts">
                <span>{tariff.billing_model === "traffic" ? at("tariff_model_traffic", {}, "Трафик") : at("tariff_model_periods", {}, "Периоды")}</span>
                <span>{tariffPriceSummary(tariff)}</span>
                <span>{at("tariff_squads", {}, "Squads")}: {(tariff.squad_uuids || []).length}</span>
                <span>{at("tariff_premium", {}, "Premium")}: {(tariff.premium_squad_uuids || []).length ? `${tariff.premium_monthly_gb || 0} GB` : "—"}</span>
                <span>{at("tariff_devices", {}, "Устройства")}: {tariff.hwid_device_limit ?? "env"}</span>
              </div>
              <div class="admin-tariff-actions">
                <AdminButton size="sm" onclick={() => tariffsStore.openEditTariff(tariff)}>
                  {at("btn_configure", {}, "Настроить")}
                </AdminButton>
                <AdminButton size="sm" onclick={() => tariffsStore.toggleTariffEnabled(tariff)} disabled={tariffsSaving}>
                  {tariff.enabled === false ? at("btn_enable", {}, "Включить") : at("btn_disable", {}, "Выключить")}
                </AdminButton>
                <AdminButton
                  size="sm"
                  onclick={() => tariffsStore.setDefaultTariff(tariff.key)}
                  disabled={tariffsSaving || tariff.enabled === false || tariff.key === tariffsCatalog.default_tariff}
                >
                  {at("btn_set_default", {}, "По умолчанию")}
                </AdminButton>
                <AdminButton
                  size="sm"
                  variant="danger"
                  onclick={() => tariffsStore.updateState({ tariffDeleteTarget: tariff, tariffDeleteOpen: true })}
                  disabled={tariffsSaving}
                  aria-label={at("btn_delete_tariff", {}, "Удалить тариф")}
                >
                  <Trash2 size={13} />
                </AdminButton>
              </div>
            </article>
          {/each}
        </div>
      {/if}
    </div>
  </article>
{/if}
