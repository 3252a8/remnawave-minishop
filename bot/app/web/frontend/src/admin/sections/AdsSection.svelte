<script>
  import { Trash2 } from "lucide-svelte";
  import { getContext, onMount } from "svelte";
  import Dialog from "../../lib/components/ui/dialog.svelte";
  import { Label } from "bits-ui";

  export let at;
  export let fmtMoney;

  const adsStore = getContext("adsStore");

  $: ({
    ads,
    adsTotals,
    adsLoading,
    adCreateOpen,
    adDraft,
  } = $adsStore);

  onMount(() => {
    adsStore.loadAds();
  });
</script>

<div class="admin-table-wrap">
  {#if adsLoading}
    <table class="admin-table admin-table-skeleton" aria-hidden="true">
      <thead>
        <tr>
          <th>{at("id", {}, "ID")}</th>
          <th>{at("ads_col_source", {}, "Источник")}</th>
          <th>{at("ads_col_param", {}, "Параметр")}</th>
          <th>{at("ads_col_cost", {}, "Стоимость")}</th>
          <th>{at("ads_col_registrations", {}, "Регистрации")}</th>
          <th>{at("ads_col_conversions", {}, "Конверсии")}</th>
          <th>{at("ads_col_status", {}, "Статус")}</th>
          <th class="admin-cell-actions">{at("actions", {}, "Действия")}</th>
        </tr>
      </thead>
      <tbody>
        {#each Array(6) as _, i (i)}
          <tr>
            <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span></td>
            <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span></td>
            <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span></td>
            <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span></td>
            <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span></td>
            <td><span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"></span></td>
            <td><span class="admin-skeleton admin-skeleton-badge"></span></td>
            <td><span class="admin-skeleton admin-skeleton-line"></span></td>
          </tr>
        {/each}
      </tbody>
    </table>
  {:else if !ads.length}
    <div class="admin-card-body"><span class="admin-muted">{at("ads_empty", {}, "Кампаний нет")}</span></div>
  {:else}
    <table class="admin-table">
      <thead>
        <tr>
          <th>{at("id", {}, "ID")}</th>
          <th>{at("ads_col_source", {}, "Источник")}</th>
          <th>{at("ads_col_param", {}, "Параметр")}</th>
          <th>{at("ads_col_cost", {}, "Стоимость")}</th>
          <th>{at("ads_col_registrations", {}, "Регистрации")}</th>
          <th>{at("ads_col_conversions", {}, "Конверсии")}</th>
          <th>{at("ads_col_status", {}, "Статус")}</th>
          <th class="admin-cell-actions">{at("actions", {}, "Действия")}</th>
        </tr>
      </thead>
      <tbody>
        {#each ads as ad}
          <tr>
            <td class="admin-cell-id" data-label={at("id", {}, "ID")}>#{ad.id}</td>
            <td data-label={at("ads_col_source", {}, "Источник")}>{ad.source}</td>
            <td class="admin-cell-mono" data-label={at("ads_col_param", {}, "Параметр")}>{ad.start_param}</td>
            <td data-label={at("ads_col_cost", {}, "Стоимость")}>{fmtMoney(ad.cost)}</td>
            <td data-label={at("ads_col_registrations", {}, "Регистрации")}>{ad.stats?.registrations ?? 0}</td>
            <td data-label={at("ads_col_conversions", {}, "Конверсии")}>{ad.stats?.conversions ?? 0}</td>
            <td data-label={at("ads_col_status", {}, "Статус")}>
              {#if ad.is_active}
                <span class="admin-badge admin-badge-success">{at("status_active", {}, "Активна")}</span>
              {:else}
                <span class="admin-badge admin-badge-muted">{at("status_disabled", {}, "Выключена")}</span>
              {/if}
            </td>
            <td class="admin-cell-actions" data-label={at("actions", {}, "Действия")}>
              <button type="button" class="admin-btn admin-btn-sm" on:click={() => adsStore.toggleAd(ad)}>
                {ad.is_active ? at("btn_disable", {}, "Выкл") : at("btn_enable", {}, "Вкл")}
              </button>
              <button type="button" class="admin-btn admin-btn-sm admin-btn-danger" on:click={() => adsStore.deleteAd(ad)}>
                <Trash2 size={13} />
              </button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<Dialog
  open={adCreateOpen}
  title={at("ad_create_title", {}, "Новая кампания")}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={() => adsStore.setCreateOpen(false)}
  class="admin-dialog admin-dialog-compact"
>
  <div class="admin-form" data-dialog-content>
    <div class="admin-dialog-form-section">
      <Label.Root class="admin-field-label">
        <span>{at("ad_label_source", {}, "Источник")}</span>
        <input class="input" type="text" placeholder="telegram_ads" value={adDraft.source} on:input={(e) => adsStore.updateDraft({ source: e.target.value })} />
      </Label.Root>
      <Label.Root class="admin-field-label">
        <span>{at("ad_label_param", {}, "start-параметр")}</span>
        <small>{at("ad_hint_param", {}, "Передаётся в /start, должен быть уникален")}</small>
        <input class="input" type="text" placeholder="ads_summer25" value={adDraft.start_param} on:input={(e) => adsStore.updateDraft({ start_param: e.target.value })} />
      </Label.Root>
    </div>
    <div class="admin-dialog-form-section">
      <Label.Root class="admin-field-label">
        <span>{at("ad_label_cost", {}, "Стоимость, RUB")}</span>
        <input class="input" type="number" step="0.01" min="0" value={adDraft.cost} on:input={(e) => adsStore.updateDraft({ cost: Number(e.target.value) })} />
      </Label.Root>
    </div>
    <div class="admin-dialog-actions">
      <button type="button" class="admin-btn" on:click={() => adsStore.setCreateOpen(false)}>{at("btn_cancel", {}, "Отмена")}</button>
      <button type="button" class="admin-btn admin-btn-primary" on:click={adsStore.createAd} disabled={!adDraft.source.trim() || !adDraft.start_param.trim()}>
        {at("btn_create", {}, "Создать")}
      </button>
    </div>
  </div>
</Dialog>
