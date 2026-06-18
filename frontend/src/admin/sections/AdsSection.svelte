<script>
  import { Input } from "$components/ui/index.js";
  import { Trash2 } from "$components/ui/icons.js";
  import { getContext, onMount } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminField,
    AdminPagination,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
  import { createAdminDatatable, syncAdminDatatable } from "../../lib/admin/datatables.js";

  export let at;
  export let fmtMoney;

  const ADS_PAGE_SIZE = 10;
  const adsStore = getContext("adsStore");
  const adsTable = createAdminDatatable([], { rowsPerPage: ADS_PAGE_SIZE });

  $: ({ ads, adsLoading, adCreateOpen, adDraft } = $adsStore);
  $: syncAdminDatatable(adsTable, ads);
  $: if (adsTable.currentPage > adsTable.pageCount) adsTable.setPage(adsTable.pageCount || 1);
  $: adHeaders = [
    at("id", {}, "ID"),
    at("ads_col_source", {}, "Источник"),
    at("ads_col_param", {}, "Параметр"),
    at("ads_col_cost", {}, "Стоимость"),
    at("ads_col_registrations", {}, "Регистрации"),
    at("ads_col_conversions", {}, "Конверсии"),
    at("ads_col_status", {}, "Статус"),
    at("actions", {}, "Действия"),
  ];

  onMount(() => {
    adsStore.loadAds();
  });
</script>

<div class="admin-table-wrap">
  {#if adsLoading}
    <AdminTableSkeleton
      headers={adHeaders}
      rows={6}
      actionColumn
      widths={["44px", "96px", "110px", "70px", "54px", "54px", "72px", "92px"]}
    />
  {:else if !ads.length}
    <AdminEmptyState tone="card"
      ><span class="admin-muted">{at("ads_empty", {}, "Кампаний нет")}</span></AdminEmptyState
    >
  {:else}
    <AdminTable>
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
        {#each adsTable.rows as ad (ad.id)}
          <tr>
            <td class="admin-cell-id" data-label={at("id", {}, "ID")}>#{ad.id}</td>
            <td data-label={at("ads_col_source", {}, "Источник")}>{ad.source}</td>
            <td class="admin-cell-mono" data-label={at("ads_col_param", {}, "Параметр")}
              >{ad.start_param}</td
            >
            <td data-label={at("ads_col_cost", {}, "Стоимость")}>{fmtMoney(ad.cost)}</td>
            <td data-label={at("ads_col_registrations", {}, "Регистрации")}
              >{ad.stats?.registrations ?? 0}</td
            >
            <td data-label={at("ads_col_conversions", {}, "Конверсии")}
              >{ad.stats?.conversions ?? 0}</td
            >
            <td data-label={at("ads_col_status", {}, "Статус")}>
              {#if ad.is_active}
                <AdminBadge variant="success">{at("status_active", {}, "Активна")}</AdminBadge>
              {:else}
                <AdminBadge variant="muted">{at("status_disabled", {}, "Выключена")}</AdminBadge>
              {/if}
            </td>
            <td class="admin-cell-actions" data-label={at("actions", {}, "Действия")}>
              <AdminButton size="sm" onclick={() => adsStore.toggleAd(ad)}>
                {ad.is_active ? at("btn_disable", {}, "Выкл") : at("btn_enable", {}, "Вкл")}
              </AdminButton>
              <AdminButton size="sm" variant="danger" onclick={() => adsStore.deleteAd(ad)}>
                <Trash2 size={13} />
              </AdminButton>
            </td>
          </tr>
        {/each}
      </tbody>
    </AdminTable>
    {#if ads.length > ADS_PAGE_SIZE}
      <AdminPagination
        table={adsTable}
        pageLabel={at("page_short", {}, "Стр.")}
        ofLabel={at("pagination_of", {}, "из")}
        totalLabel={at("total", {}, "Всего")}
        jumpLabel={at("page_short", {}, "Стр.")}
        jumpAriaLabel={at("pagination_jump_aria", {}, "Перейти к странице")}
        goLabel={at("pagination_go", {}, "Перейти")}
        prevLabel={at("back", {}, "Назад")}
        nextLabel={at("next", {}, "Далее")}
      />
    {/if}
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
      <AdminField label={at("ad_label_source", {}, "Источник")}>
        <Input
          class="input"
          type="text"
          placeholder="telegram_ads"
          value={adDraft.source}
          on:input={(e) => adsStore.updateDraft({ source: e.target.value })}
        />
      </AdminField>
      <AdminField
        label={at("ad_label_param", {}, "start-параметр")}
        hint={at("ad_hint_param", {}, "Передаётся в /start, должен быть уникален")}
      >
        <Input
          class="input"
          type="text"
          placeholder="ads_summer25"
          value={adDraft.start_param}
          on:input={(e) => adsStore.updateDraft({ start_param: e.target.value })}
        />
      </AdminField>
    </div>
    <div class="admin-dialog-form-section">
      <AdminField label={at("ad_label_cost", {}, "Стоимость, RUB")}>
        <Input
          class="input"
          type="number"
          step="0.01"
          min="0"
          value={adDraft.cost}
          on:input={(e) => adsStore.updateDraft({ cost: Number(e.target.value) })}
        />
      </AdminField>
    </div>
    <div class="admin-dialog-actions">
      <AdminButton onclick={() => adsStore.setCreateOpen(false)}
        >{at("btn_cancel", {}, "Отмена")}</AdminButton
      >
      <AdminButton
        variant="primary"
        onclick={adsStore.createAd}
        disabled={!adDraft.source.trim() || !adDraft.start_param.trim()}
      >
        {at("btn_create", {}, "Создать")}
      </AdminButton>
    </div>
  </div>
</Dialog>
