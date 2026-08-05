<script lang="ts">
  import { getAdsStore } from "$lib/admin/context";
  import { Input } from "$components/ui/index.js";
  import { Trash2 } from "$components/ui/icons.js";
  import { onMount } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminField,
    AdminPagination,
    AdminSortableHeader,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
  import { TableHandler } from "@vincjo/datatables";
  import type { components } from "../../lib/api/openapi.generated";
  import { sortAdminRows, type AdminSortColumn } from "$lib/admin/tableSort.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Ad = components["schemas"]["AdOut"];
  type AdDraft = components["schemas"]["AdCreateBody"];

  let {
    at,
    fmtMoney,
  }: {
    at: TranslateFn;
    fmtMoney: (value: number) => string;
  } = $props();

  const ADS_PAGE_SIZE = 10;
  const adsStore = getAdsStore();
  const adsTable = new TableHandler<Ad>([], { rowsPerPage: ADS_PAGE_SIZE });
  let adsSort = $state("id_desc");

  const ads = $derived(adsStore.ads as Ad[]);
  const adsLoading = $derived(Boolean(adsStore.adsLoading));
  const adCreateOpen = $derived(Boolean(adsStore.adCreateOpen));
  const adDraft = $derived(
    (adsStore.adDraft || { source: "", start_param: "", cost: 0 }) as AdDraft
  );
  const adRows = $derived(adsTable.rows as Ad[]);

  const adSortColumns = [
    { asc: "id_asc", desc: "id_desc", defaultDirection: "desc", value: (ad) => ad.id },
    { asc: "source_asc", desc: "source_desc", defaultDirection: "asc", value: (ad) => ad.source },
    {
      asc: "param_asc",
      desc: "param_desc",
      defaultDirection: "asc",
      value: (ad) => ad.start_param,
    },
    { asc: "cost_asc", desc: "cost_desc", defaultDirection: "desc", value: (ad) => ad.cost },
    {
      asc: "registrations_asc",
      desc: "registrations_desc",
      defaultDirection: "desc",
      value: (ad) => adStat(ad, "registrations"),
    },
    {
      asc: "conversions_asc",
      desc: "conversions_desc",
      defaultDirection: "desc",
      value: (ad) => adStat(ad, "conversions"),
    },
    {
      asc: "status_asc",
      desc: "status_desc",
      defaultDirection: "desc",
      value: (ad) => ad.is_active,
    },
  ] satisfies AdminSortColumn<Ad>[];

  $effect(() => {
    adsTable.setRows(sortAdminRows(ads, adsSort, adSortColumns));
    if (adsTable.currentPage > (adsTable.pageCount || 1)) adsTable.setPage(adsTable.pageCount || 1);
  });
  const adHeaders = $derived([
    at("id", {}, "ID"),
    at("ads_col_source", {}, "Source"),
    at("ads_col_param", {}, "Parameter"),
    at("ads_col_cost", {}, "Cost"),
    at("ads_col_registrations", {}, "Registrations"),
    at("ads_col_conversions", {}, "Conversions"),
    at("ads_col_status", {}, "Status"),
    at("actions", {}, "Actions"),
  ]);

  onMount(() => {
    adsStore.loadAds();
  });

  function adStat(ad: Ad, key: string): number {
    const raw = ad.stats?.[key];
    const value = Number(raw);
    return Number.isFinite(value) ? value : 0;
  }

  function setAdsSort(sort: string): void {
    adsSort = sort;
    adsTable.setPage(1);
  }
</script>

<div class="admin-table-wrap">
  {#if adsLoading}
    <AdminTableSkeleton
      headers={adHeaders}
      rows={6}
      rowHeight={58}
      actionColumn
      widths={["44px", "96px", "110px", "70px", "54px", "54px", "72px", "92px"]}
    />
  {:else if !ads.length}
    <AdminEmptyState tone="card"
      ><span class="admin-muted">{at("ads_empty", {}, "No campaigns found")}</span></AdminEmptyState
    >
  {:else}
    <AdminTable>
      <thead>
        <tr>
          <AdminSortableHeader
            label={at("id", {}, "ID")}
            column={adSortColumns[0]}
            currentSort={adsSort}
            {at}
            onSort={setAdsSort}
          />
          <AdminSortableHeader
            label={at("ads_col_source", {}, "Source")}
            column={adSortColumns[1]}
            currentSort={adsSort}
            {at}
            onSort={setAdsSort}
          />
          <AdminSortableHeader
            label={at("ads_col_param", {}, "Parameter")}
            column={adSortColumns[2]}
            currentSort={adsSort}
            {at}
            onSort={setAdsSort}
          />
          <AdminSortableHeader
            label={at("ads_col_cost", {}, "Cost")}
            column={adSortColumns[3]}
            currentSort={adsSort}
            {at}
            onSort={setAdsSort}
          />
          <AdminSortableHeader
            label={at("ads_col_registrations", {}, "Registrations")}
            column={adSortColumns[4]}
            currentSort={adsSort}
            {at}
            onSort={setAdsSort}
          />
          <AdminSortableHeader
            label={at("ads_col_conversions", {}, "Conversions")}
            column={adSortColumns[5]}
            currentSort={adsSort}
            {at}
            onSort={setAdsSort}
          />
          <AdminSortableHeader
            label={at("ads_col_status", {}, "Status")}
            column={adSortColumns[6]}
            currentSort={adsSort}
            {at}
            onSort={setAdsSort}
          />
          <th class="admin-cell-actions">{at("actions", {}, "Actions")}</th>
        </tr>
      </thead>
      <tbody>
        {#each adRows as ad (ad.id)}
          <tr>
            <td class="admin-cell-id" data-label={at("id", {}, "ID")}>#{ad.id}</td>
            <td data-label={at("ads_col_source", {}, "Source")}>{ad.source}</td>
            <td class="admin-cell-mono" data-label={at("ads_col_param", {}, "Parameter")}
              >{ad.start_param}</td
            >
            <td data-label={at("ads_col_cost", {}, "Cost")}>{fmtMoney(ad.cost)}</td>
            <td data-label={at("ads_col_registrations", {}, "Registrations")}
              >{adStat(ad, "registrations")}</td
            >
            <td data-label={at("ads_col_conversions", {}, "Conversions")}
              >{adStat(ad, "conversions")}</td
            >
            <td data-label={at("ads_col_status", {}, "Status")}>
              {#if ad.is_active}
                <AdminBadge variant="success">{at("status_active", {}, "Active")}</AdminBadge>
              {:else}
                <AdminBadge variant="muted">{at("status_disabled", {}, "Disabled")}</AdminBadge>
              {/if}
            </td>
            <td class="admin-cell-actions" data-label={at("actions", {}, "Actions")}>
              <AdminButton size="sm" onclick={() => adsStore.toggleAd(ad)}>
                {ad.is_active ? at("btn_disable", {}, "Off") : at("btn_enable", {}, "On")}
              </AdminButton>
              <AdminButton
                size="sm"
                variant="danger"
                title={at("btn_delete", {}, "Delete")}
                aria-label={at("btn_delete", {}, "Delete")}
                onclick={() => adsStore.deleteAd(ad)}
              >
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
        pageLabel={at("page_short", {}, "Page")}
        ofLabel={at("pagination_of", {}, "of")}
        totalLabel={at("total", {}, "Total")}
        jumpLabel={at("page_short", {}, "Page")}
        jumpAriaLabel={at("pagination_jump_aria", {}, "Go to page")}
        goLabel={at("pagination_go", {}, "Go")}
        prevLabel={at("back", {}, "Back")}
        nextLabel={at("next", {}, "Next")}
      />
    {/if}
  {/if}
</div>

<Dialog
  open={adCreateOpen}
  title={at("ad_create_title", {}, "New campaign")}
  closeLabel={at("close", {}, "Close")}
  onclose={() => adsStore.setCreateOpen(false)}
  class="admin-dialog admin-dialog-compact admin-ad-dialog"
>
  <div class="admin-form" data-dialog-content>
    <div class="admin-dialog-form-section">
      <AdminField label={at("ad_label_source", {}, "Source")}>
        <Input
          class="input"
          type="text"
          placeholder="telegram_ads"
          value={adDraft.source}
          oninput={(e) =>
            adsStore.updateDraft({ source: (e.currentTarget as HTMLInputElement).value })}
        />
      </AdminField>
      <AdminField
        label={at("ad_label_param", {}, "start parameter")}
        hint={at("ad_hint_param", {}, "Unique identifier for the referral link")}
      >
        <Input
          class="input"
          type="text"
          placeholder="ads_summer25"
          value={adDraft.start_param}
          oninput={(e) =>
            adsStore.updateDraft({ start_param: (e.currentTarget as HTMLInputElement).value })}
        />
      </AdminField>
    </div>
    <div class="admin-dialog-form-section">
      <AdminField label={at("ad_label_cost", {}, "Cost, RUB")}>
        <Input
          class="input"
          type="number"
          step="0.01"
          min="0"
          value={String(adDraft.cost)}
          oninput={(e) =>
            adsStore.updateDraft({ cost: Number((e.currentTarget as HTMLInputElement).value) })}
        />
      </AdminField>
    </div>
    <div class="admin-dialog-actions">
      <AdminButton onclick={() => adsStore.setCreateOpen(false)}
        >{at("btn_cancel", {}, "Cancel")}</AdminButton
      >
      <AdminButton
        variant="primary"
        onclick={adsStore.createAd}
        disabled={!adDraft.source.trim() || !adDraft.start_param.trim()}
      >
        {at("btn_create", {}, "Create")}
      </AdminButton>
    </div>
  </div>
</Dialog>
