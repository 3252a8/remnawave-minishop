<script lang="ts">
  import { getAdsStore } from "$lib/admin/context";
  import { Input, DateInput } from "$components/ui/index.js";
  import AdWorkspace from "./advertising/AdWorkspace.svelte";
  import AdUnassignedPanel from "./advertising/AdUnassignedPanel.svelte";
  import { onMount } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminSelect,
    AdminEmptyState,
    AdminField,
    AdminFormGrid,
    AdminListToolbar,
    AdminSettingsGroup,
    AdminPagination,
    AdminSortableHeader,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
  import { adConversionCount, adRegistrationCount } from "$lib/admin/adStats";
  import type { components } from "../../lib/api/openapi.generated";
  import type { AdminSortColumn } from "$lib/admin/tableSort.js";
  import { Tabs } from "$components/ui/primitives.js";
  import { ArrowRight, RefreshCw } from "$components/ui/icons.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Ad = components["schemas"]["AdOut"];
  type AdDraft = components["schemas"]["AdCreateBody"];

  let {
    at,
    fmtMoney,
    appRepositoryUrl = "https://dev.minishop.minidoc.cc/",
  }: {
    at: TranslateFn;
    fmtMoney: (value: number) => string;
    appRepositoryUrl?: string;
  } = $props();

  const ADS_PAGE_SIZE = 10;
  const adsStore = getAdsStore();
  let adsSort = $state("id_desc");
  let selectedCampaign = $state<number | null>(null);
  let view = $state("campaigns");
  let createPending = $state(false);
  let query = $state("");
  let status = $state("all");
  let since = $state("");
  let until = $state("");
  function filter(page = 0) {
    void adsStore.loadAds(page, {
      search: query,
      status,
      sort: adsSort,
      ...(since ? { start: `${since}T00:00:00Z` } : {}),
      ...(until ? { end: `${until}T00:00:00Z` } : {}),
    });
  }

  const ads = $derived(adsStore.ads as Ad[]);
  const adsLoading = $derived(Boolean(adsStore.adsLoading));
  const adCreateOpen = $derived(Boolean(adsStore.adCreateOpen));
  const adDraft = $derived(
    (adsStore.adDraft || { source: "", start_param: "", cost: 0 }) as AdDraft
  );
  const adPurchasesOpen = $derived(Boolean(adsStore.adPurchasesOpen));
  const adPurchasesLoading = $derived(Boolean(adsStore.adPurchasesLoading));
  const adPurchasesList = $derived(adsStore.adPurchasesList || []);
  const adRows = $derived(ads);

  const adSortColumns = [
    { asc: "id_asc", desc: "id_desc", defaultDirection: "desc", value: (ad) => ad.id },
    { asc: "source_asc", desc: "source_desc", defaultDirection: "asc", value: (ad) => ad.source },
    {
      asc: "param_asc",
      desc: "param_desc",
      defaultDirection: "asc",
      value: (ad) => ad.start_param,
    },
    {
      asc: "advertiser_asc",
      desc: "advertiser_desc",
      defaultDirection: "asc",
      value: (ad) => ad.advertiser_id ?? 0,
    },
    { asc: "cost_asc", desc: "cost_desc", defaultDirection: "desc", value: (ad) => ad.cost },
    {
      asc: "registrations_asc",
      desc: "registrations_desc",
      defaultDirection: "desc",
      value: (ad) => adRegistrationCount(ad.stats),
    },
    {
      asc: "conversions_asc",
      desc: "conversions_desc",
      defaultDirection: "desc",
      value: (ad) => adConversionCount(ad.stats),
    },
    {
      asc: "status_asc",
      desc: "status_desc",
      defaultDirection: "desc",
      value: (ad) => ad.is_active,
    },
  ] satisfies AdminSortColumn<Ad>[];

  const sortItems = $derived(
    adSortColumns.flatMap((column, index) => {
      const label = at(
        [
          "id",
          "ads_col_source",
          "ads_col_param",
          "ads_col_advertiser",
          "ads_col_cost",
          "ads_col_registrations",
          "ads_col_conversions",
          "ads_col_status",
        ][index]
      );
      return [
        { value: column.asc, label: `${label} ↑` },
        { value: column.desc, label: `${label} ↓` },
      ];
    })
  );
  const adHeaders = $derived([
    at("ads_campaign"),
    at("ads_col_advertiser"),
    at("ads_col_cost"),
    at("ads_col_registrations"),
    at("ads_col_conversions"),
    at("ads_col_status"),
    at("actions"),
  ]);

  onMount(() => {
    adsStore.loadAds();
  });

  function setAdsSort(sort: string): void {
    adsSort = sort;
    filter();
  }

  function resetFilters() {
    query = "";
    status = "all";
    since = "";
    until = "";
    adsSort = "id_desc";
    filter();
  }
  async function submitCampaign() {
    if (createPending) return;
    createPending = true;
    try {
      await adsStore.createAd();
    } finally {
      createPending = false;
    }
  }
</script>

<div class="ads-page">
  {#if selectedCampaign !== null}
    <AdWorkspace
      campaignId={selectedCampaign}
      documentationUrl={appRepositoryUrl}
      {at}
      onback={() => {
        selectedCampaign = null;
      }}
    />
  {:else}
    <Tabs.Root class="admin-tabs-root" bind:value={view}>
      <Tabs.List class="admin-tabs-list" aria-label={at("ads_navigation")}>
        <Tabs.Trigger class="admin-tabs-trigger" value="campaigns"
          >{at("ads_campaigns")}</Tabs.Trigger
        >
        <Tabs.Trigger class="admin-tabs-trigger" value="unassigned"
          >{at("ads_unassigned")}</Tabs.Trigger
        >
      </Tabs.List>
    </Tabs.Root>
    {#if view === "unassigned"}
      <AdUnassignedPanel {at} />
    {:else}
      <AdminListToolbar
        total={adsStore.adsTotal}
        totalLabel={at("total")}
        columns={4}
        mobileColumns={1}
        onsubmit={() => filter()}
      >
        {#snippet search()}
          <Input
            type="search"
            bind:value={query}
            placeholder={at("ads_search_placeholder")}
            aria-label={at("search")}
          />
        {/snippet}
        {#snippet searchActions()}<AdminButton variant="primary" type="submit" disabled={adsLoading}
            >{at("ads_apply_filters")}</AdminButton
          >{/snippet}
        {#snippet filters()}
          <AdminField label={at("ads_status")}
            ><AdminSelect
              bind:value={status}
              items={["all", "active", "paused", "archived"].map((value) => ({
                value,
                label: at(`ads_${value}`),
              }))}
              ariaLabel={at("ads_status")}
            /></AdminField
          >
          <AdminField label={at("ads_created_from")}
            ><DateInput
              bind:value={since}
              ariaLabel={at("ads_created_from")}
              locale={at("ads_calendar_locale")}
              clearLabel={at("ads_clear_date")}
            /></AdminField
          >
          <AdminField label={at("ads_created_until")}
            ><DateInput
              bind:value={until}
              ariaLabel={at("ads_created_until")}
              locale={at("ads_calendar_locale")}
              clearLabel={at("ads_clear_date")}
            /></AdminField
          >
          <AdminField label={at("sort")}
            ><AdminSelect
              bind:value={adsSort}
              items={sortItems}
              ariaLabel={at("sort")}
              onValueChange={setAdsSort}
            /></AdminField
          >
        {/snippet}
        {#snippet actions()}
          <AdminButton onclick={resetFilters} disabled={adsLoading}
            >{at("reset_filters")}</AdminButton
          >
          <AdminButton
            variant="ghost"
            onclick={() => filter(adsStore.adsPage)}
            disabled={adsLoading}><RefreshCw size={15} />{at("refresh")}</AdminButton
          >
        {/snippet}
      </AdminListToolbar>
      {#if adsStore.adsError}<AdminEmptyState tone="card"
          ><p role="alert">{adsStore.adsError}</p>
          <AdminButton onclick={() => filter()}>{at("retry")}</AdminButton></AdminEmptyState
        >{/if}
      {#if adsLoading}
        <AdminTableSkeleton
          headers={adHeaders}
          rows={6}
          rowHeight={76}
          actionColumn
          widths={["30%", "12%", "12%", "12%", "10%", "12%", "12%"]}
        />
      {:else if !ads.length}
        <AdminEmptyState tone="card"
          ><span class="admin-muted">{at("ads_empty", {}, "No campaigns found")}</span
          ></AdminEmptyState
        >
      {:else}
        <AdminTable layout="fixed" minWidth="1120px" class="ads-campaign-table">
          <colgroup
            ><col style="width:30%" /><col style="width:12%" /><col style="width:12%" /><col
              style="width:12%"
            /><col style="width:10%" /><col style="width:12%" /><col style="width:12%" /></colgroup
          >
          <thead
            ><tr>
              <AdminSortableHeader
                label={at("ads_campaign")}
                column={adSortColumns[1]}
                currentSort={adsSort}
                {at}
                onSort={setAdsSort}
              />
              <AdminSortableHeader
                label={at("ads_col_advertiser")}
                column={adSortColumns[3]}
                currentSort={adsSort}
                {at}
                onSort={setAdsSort}
              />
              <AdminSortableHeader
                label={at("ads_col_cost")}
                column={adSortColumns[4]}
                currentSort={adsSort}
                {at}
                onSort={setAdsSort}
              />
              <AdminSortableHeader
                label={at("ads_col_registrations")}
                column={adSortColumns[5]}
                currentSort={adsSort}
                {at}
                onSort={setAdsSort}
              />
              <AdminSortableHeader
                label={at("ads_col_conversions")}
                column={adSortColumns[6]}
                currentSort={adsSort}
                {at}
                onSort={setAdsSort}
              />
              <AdminSortableHeader
                label={at("ads_col_status")}
                column={adSortColumns[7]}
                currentSort={adsSort}
                {at}
                onSort={setAdsSort}
              />
              <th>{at("actions")}</th>
            </tr></thead
          >
          <tbody
            >{#each adRows as ad (ad.id)}<tr>
                <td class="admin-cell-primary" data-label={at("ads_campaign")}
                  ><div class="ads-campaign-identity">
                    <strong>{ad.name || ad.source}</strong><small>#{ad.id} · {ad.source}</small
                    ><code>{ad.start_param}</code>
                  </div></td
                >
                <td class="admin-cell-mono" data-label={at("ads_col_advertiser")}
                  >{ad.advertiser_id || "—"}</td
                >
                <td class="ads-number" data-label={at("ads_col_cost")}
                  >{fmtMoney(ad.cost)} <small>RUB</small></td
                >
                <td class="ads-number" data-label={at("ads_col_registrations")}
                  >{adRegistrationCount(ad.stats)}</td
                >
                <td class="ads-number" data-label={at("ads_col_conversions")}
                  >{adConversionCount(ad.stats)}</td
                >
                <td data-label={at("ads_col_status")}
                  ><AdminBadge
                    variant={ad.archived_at ? "muted" : ad.is_active ? "success" : "warning"}
                    >{ad.archived_at
                      ? at("ads_archived")
                      : ad.is_active
                        ? at("ads_active")
                        : at("ads_paused")}</AdminBadge
                  ></td
                >
                <td class="admin-cell-actions" data-label={at("actions")}
                  ><div class="ads-row-actions">
                    <AdminButton
                      size="sm"
                      aria-label={at("ads_open_campaign")}
                      onclick={() => {
                        selectedCampaign = ad.id;
                      }}><ArrowRight size={14} />{at("ads_open_short")}</AdminButton
                    >
                  </div></td
                >
              </tr>{/each}</tbody
          >
        </AdminTable>
        {#if adsStore.adsTotal > ADS_PAGE_SIZE}<AdminPagination
            page={adsStore.adsPage}
            pageCount={Math.ceil(adsStore.adsTotal / ADS_PAGE_SIZE)}
            total={adsStore.adsTotal}
            onPageChange={(page) => filter(page)}
            pageLabel={at("page_short")}
            ofLabel={at("pagination_of")}
            totalLabel={at("total")}
            jumpLabel={at("page_short")}
            jumpAriaLabel={at("pagination_jump_aria")}
            goLabel={at("pagination_go")}
            prevLabel={at("back")}
            nextLabel={at("next")}
          />{/if}
      {/if}
    {/if}
  {/if}
</div>

<Dialog
  open={adCreateOpen}
  title={at("ad_create_title")}
  description={at("ads_create_description")}
  closeLabel={at("close")}
  onclose={() => {
    if (!createPending) adsStore.setCreateOpen(false);
  }}
  class="admin-dialog admin-ad-dialog"
>
  <form
    class="ads-create-form"
    data-dialog-content
    onsubmit={(event) => {
      event.preventDefault();
      void submitCampaign();
    }}
  >
    <AdminSettingsGroup
      title={at("ads_create_identity")}
      description={at("ads_create_identity_hint")}
    >
      <AdminFormGrid>
        <AdminField label={at("ad_label_source")}
          ><Input
            type="text"
            required
            maxlength={160}
            placeholder="telegram_ads"
            value={adDraft.source}
            disabled={createPending}
            oninput={(event) => adsStore.updateDraft({ source: event.currentTarget.value })}
          /></AdminField
        >
        <AdminField label={at("ad_label_param")} hint={at("ad_hint_param")}
          ><Input
            type="text"
            required
            minlength={2}
            maxlength={64}
            placeholder="ads_campaign_2026"
            value={adDraft.start_param}
            disabled={createPending}
            oninput={(event) => adsStore.updateDraft({ start_param: event.currentTarget.value })}
          /></AdminField
        >
      </AdminFormGrid>
    </AdminSettingsGroup>
    <AdminSettingsGroup
      title={at("ads_create_accounting")}
      description={at("ads_create_accounting_hint")}
    >
      <AdminFormGrid>
        <AdminField label={at("ad_label_cost")}
          ><Input
            type="number"
            step="0.01"
            min="0"
            max="100000000"
            value={String(adDraft.cost)}
            disabled={createPending}
            oninput={(event) => adsStore.updateDraft({ cost: Number(event.currentTarget.value) })}
          /></AdminField
        >
        <AdminField label={at("ad_label_advertiser")} hint={at("ad_hint_advertiser")}
          ><Input
            type="number"
            min="1"
            step="1"
            placeholder="910000001"
            value={adDraft.advertiser_id ? String(adDraft.advertiser_id) : ""}
            disabled={createPending}
            oninput={(event) =>
              adsStore.updateDraft({
                advertiser_id: event.currentTarget.value ? Number(event.currentTarget.value) : null,
              })}
          /></AdminField
        >
      </AdminFormGrid>
    </AdminSettingsGroup>
    <div class="ads-form-actions">
      <AdminButton disabled={createPending} onclick={() => adsStore.setCreateOpen(false)}
        >{at("btn_cancel")}</AdminButton
      ><AdminButton
        type="submit"
        variant="primary"
        disabled={createPending ||
          !adDraft.source.trim() ||
          !adDraft.start_param.trim() ||
          !Number.isFinite(adDraft.cost)}
        >{createPending ? at("loading") : at("btn_create")}</AdminButton
      >
    </div>
  </form>
</Dialog>
<Dialog
  open={adPurchasesOpen}
  title={at("ad_purchases_title", {}, "Campaign Purchases")}
  closeLabel={at("close", {}, "Close")}
  onclose={() => adsStore.setPurchasesOpen(false)}
  class="admin-dialog"
>
  <div class="admin-dialog-content" data-dialog-content>
    {#if adPurchasesLoading}
      <div style="padding: 24px; text-align: center; color: var(--admin-muted-fg);">
        {at("loading", {}, "Loading...")}
      </div>
    {:else if !adPurchasesList.length}
      <AdminEmptyState tone="card">
        <span class="admin-muted">{at("ad_purchases_empty", {}, "No purchases yet")}</span>
      </AdminEmptyState>
    {:else}
      <AdminTable layout="fixed">
        <thead>
          <tr>
            <th>{at("id", {}, "ID")}</th>
            <th>{at("user", {}, "User")}</th>
            <th>{at("amount", {}, "Amount")}</th>
            <th>{at("description", {}, "Description")}</th>
            <th>{at("date", {}, "Date")}</th>
          </tr>
        </thead>
        <tbody>
          {#each adPurchasesList as p (p.payment_id)}
            <tr>
              <td class="admin-cell-id">#{p.payment_id}</td>
              <td>{p.username || p.user_id}</td>
              <td>{p.amount.toLocaleString()} {p.currency}</td>
              <td>{p.description || "—"}</td>
              <td>{p.created_at ? new Date(p.created_at).toLocaleString() : "—"}</td>
            </tr>
          {/each}
        </tbody>
      </AdminTable>
      <AdminPagination
        page={adsStore.adPurchasesPage}
        pageCount={Math.ceil(adsStore.adPurchasesTotal / 50)}
        total={adsStore.adPurchasesTotal}
        pageLabel={at("page_short")}
        ofLabel={at("pagination_of")}
        totalLabel={at("total")}
        prevLabel={at("back")}
        nextLabel={at("next")}
        onPageChange={(page) => {
          if (adsStore.adPurchasesAd) void adsStore.loadAdPurchases(adsStore.adPurchasesAd, page);
        }}
      />
    {/if}
  </div>
</Dialog>

<style>
  .ads-page {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  .ads-campaign-identity {
    display: grid;
    gap: 4px;
    min-width: 0;
  }
  .ads-campaign-identity strong {
    font-weight: 600;
    overflow-wrap: anywhere;
  }
  .ads-campaign-identity small,
  .ads-campaign-identity code {
    color: var(--admin-muted);
    font-size: 11px;
    overflow-wrap: anywhere;
  }
  .ads-number {
    font-variant-numeric: tabular-nums;
  }
  .ads-number small {
    color: var(--admin-muted);
    font-size: 11px;
  }
  .ads-row-actions {
    display: flex;
    justify-content: flex-start;
    gap: 8px;
  }
  .ads-create-form {
    display: grid;
    gap: 20px;
    min-width: 0;
    padding: 2px;
  }
  .ads-form-actions {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
    padding-top: 4px;
  }
  :global(.dialog-card.admin-ad-dialog) {
    width: min(100%, 840px);
  }
  @media (max-width: 720px) {
    .ads-form-actions {
      flex-wrap: wrap;
    }
    .ads-form-actions :global(.admin-btn) {
      flex: 1;
    }
  }
</style>
