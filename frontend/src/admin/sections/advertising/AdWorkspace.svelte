<script lang="ts">
  import { onMount } from "svelte";
  import { getAdsStore } from "$lib/admin/context";
  import { buildAdvertisingPath, buildAdvertisingExportPath, unwrap } from "$lib/webapp/publicApi";
  import { Input, DateInput, Textarea } from "$components/ui/index.js";
  import { Tabs } from "$components/ui/primitives.js";
  import { ArrowLeft, Download, RefreshCw } from "$components/ui/icons.js";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminButton,
    AdminCardActions,
    AdminBadge,
    AdminListToolbar,
    AdminSettingsGroup,
    AdminFormGrid,
    AdminField,
    AdminSelect,
    AdminPagination,
    AdminTable,
    AdminEmptyState,
  } from "$components/patterns/admin/index.js";
  import AdReportPanel from "./AdReportPanel.svelte";
  import AdLinksPanel from "./AdLinksPanel.svelte";
  import AdImportsPanel from "./AdImportsPanel.svelte";
  import {
    adError,
    adDate,
    adMoney,
    type AdDetail,
    type Translate,
    type AdMutation,
  } from "./types";
  let {
    campaignId,
    at,
    onback,
    documentationUrl,
  }: { campaignId: number; at: Translate; onback: () => void; documentationUrl: string } = $props();
  const store = getAdsStore();
  let data = $state.raw<AdDetail | null>(null);
  let tab = $state("overview");
  let exportKind = $state("report");
  let busy = $state(false);
  let error = $state("");
  let start = $state("");
  let end = $state("");
  let periodMode = $state("events");
  let page = $state(0);
  let linkFilter = $state(""),
    evidenceFilter = $state(""),
    channelFilter = $state(""),
    currencyFilter = $state("");
  let name = $state("");
  let description = $state("");
  let cost = $state("0");
  let reportCurrency = $state("RUB");
  let windowDays = $state("30");
  let spendSource = $state("legacy");
  let advertiser = $state("");
  let archiveOpen = $state(false);
  let resetOpen = $state(false);
  let resetPending = $state(false);
  let amount = $state("");
  let currency = $state("RUB");
  let spendDate = $state(new Date().toISOString().slice(0, 16));
  let note = $state("");
  let version = 0;
  const tabs = ["overview", "links", "offers", "contacts", "spend", "imports", "audit", "settings"];
  onMount(() => {
    void load(true);
    return () => {
      version++;
    };
  });

  async function load(initial = false) {
    const current = ++version;
    busy = true;
    error = "";
    const query = new URLSearchParams({
      period_mode: periodMode,
      page: String(page),
      page_size: "25",
    });
    if (linkFilter) query.set("link_id", linkFilter);
    if (evidenceFilter) query.set("evidence", evidenceFilter);
    if (channelFilter) query.set("channel", channelFilter);
    if (currencyFilter) query.set("currency", currencyFilter.toUpperCase());
    if (start) query.set("start", `${start}T00:00:00Z`);
    if (end) query.set("end", `${end}T00:00:00Z`);
    try {
      const result = await store.request(buildAdvertisingPath("detail", campaignId, "", query));
      if (current !== version) return;
      if (result.ok === true) {
        data = unwrap(result);
        if (initial) {
          name = data.name;
          description = data.description;
          cost = String(data.campaign.cost);
          reportCurrency = data.report_currency;
          windowDays = String(data.attribution_window_days);
          spendSource = data.spend_source;
          advertiser = data.campaign.advertiser_id ? String(data.campaign.advertiser_id) : "";
        }
      } else error = at("ads_action_failed", { reason: adError(result) });
    } catch {
      if (current === version) error = at("ads_load_failed");
    } finally {
      if (current === version) busy = false;
    }
  }
  async function mutate(
    action: AdMutation,
    body: object = {},
    childId: string | number = ""
  ): Promise<boolean> {
    if (busy) return false;
    busy = true;
    error = "";
    try {
      const result = await store.request(buildAdvertisingPath(action, campaignId, childId), {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (result.ok !== true) {
        error = at("ads_action_failed", { reason: adError(result) });
        return false;
      }
      await load();
      await store.loadAds();
      return true;
    } catch {
      error = at("ads_load_failed");
      return false;
    } finally {
      busy = false;
    }
  }
  async function download(kind: string) {
    if (!store.requestBlob) return;
    error = "";
    const query = new URLSearchParams({ kind, period_mode: periodMode });
    if (linkFilter) query.set("link_id", linkFilter);
    if (evidenceFilter) query.set("evidence", evidenceFilter);
    if (channelFilter) query.set("channel", channelFilter);
    if (currencyFilter) query.set("currency", currencyFilter.toUpperCase());
    if (start) query.set("start", `${start}T00:00:00Z`);
    if (end) query.set("end", `${end}T00:00:00Z`);
    try {
      const blob = await store.requestBlob(buildAdvertisingExportPath(campaignId, query));
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `advertising-${kind}.csv`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      error = at("ads_load_failed");
    }
  }
  async function saveSettings() {
    if (!data) return;
    if (
      await mutate("edit", {
        name,
        description,
        cost: Number(cost),
        report_currency: reportCurrency,
        attribution_window_days: Number(windowDays),
        spend_source: spendSource,
      })
    ) {
      await store.assignAdvertiser(data.campaign, advertiser ? Number(advertiser) : null);
      await load();
    }
  }
</script>

<div class="ad-workspace" aria-busy={busy}>
  <header class="ad-workspace-header">
    <AdminButton onclick={onback}><ArrowLeft size={15} />{at("ads_campaigns")}</AdminButton>
    <div class="ad-workspace-title">
      <h2>{data?.name || at("ads_campaign")}</h2>
      {#if data}<small>#{data.campaign.id} · {data.campaign.source}</small>{/if}
    </div>
    {#if data}<AdminBadge
        variant={data.archived_at ? "muted" : data.campaign.is_active ? "success" : "warning"}
        >{data.archived_at
          ? at("ads_archived")
          : data.campaign.is_active
            ? at("ads_active")
            : at("ads_paused")}</AdminBadge
      >{/if}
    <AdminButton variant="ghost" disabled={busy} onclick={() => load()}
      ><RefreshCw size={15} />{at("refresh")}</AdminButton
    >
  </header>
  <Tabs.Root class="admin-tabs-root" bind:value={tab}>
    <Tabs.List class="admin-tabs-list" aria-label={at("ads_campaign_sections")}>
      {#each tabs as item (item)}<Tabs.Trigger class="admin-tabs-trigger" value={item}
          >{at(`ads_tab_${item}`)}</Tabs.Trigger
        >{/each}
    </Tabs.List>
  </Tabs.Root>
  {#if tab === "overview" || tab === "contacts"}
    <AdminListToolbar
      columns={4}
      mobileColumns={1}
      onsubmit={() => {
        page = 0;
        void load();
      }}
    >
      {#snippet filters()}
        <AdminField label={at("ads_period_mode")}
          ><AdminSelect
            bind:value={periodMode}
            items={[
              { value: "events", label: at("ads_events_period") },
              { value: "cohort", label: at("ads_cohort_period") },
            ]}
            ariaLabel={at("ads_period_mode")}
          /></AdminField
        >
        <AdminField label={at("ads_period_start")}
          ><DateInput
            bind:value={start}
            ariaLabel={at("ads_period_start")}
            locale={at("ads_calendar_locale")}
            clearLabel={at("ads_clear_date")}
          /></AdminField
        >
        <AdminField label={at("ads_period_end")}
          ><DateInput
            bind:value={end}
            ariaLabel={at("ads_period_end")}
            locale={at("ads_calendar_locale")}
            clearLabel={at("ads_clear_date")}
          /></AdminField
        >
        <AdminField label={at("ads_link")}
          ><AdminSelect
            bind:value={linkFilter}
            items={[
              { value: "", label: at("ads_all") },
              ...(data?.links || []).map((link) => ({
                value: String(link.id),
                label: link.label || link.code,
              })),
            ]}
            ariaLabel={at("ads_link")}
          /></AdminField
        >
        <AdminField label={at("ads_evidence")}
          ><AdminSelect
            bind:value={evidenceFilter}
            items={[
              "",
              "tagged_link",
              "operator_utm_mapping",
              "promo_code",
              "legacy_bot_start",
              "unknown",
            ].map((value) => ({ value, label: value ? at(`ads_${value}`) : at("ads_all") }))}
            ariaLabel={at("ads_evidence")}
          /></AdminField
        >
        <AdminField label={at("ads_channel")}
          ><AdminSelect
            bind:value={channelFilter}
            items={["", "web", "bot", "telegram", "miniapp"].map((value) => ({
              value,
              label: value ? at(`ads_${value}`) : at("ads_all"),
            }))}
            ariaLabel={at("ads_channel")}
          /></AdminField
        >
        <AdminField label={at("ads_currency")}
          ><Input
            bind:value={currencyFilter}
            placeholder="RUB / XTR / TON"
            maxlength={8}
          /></AdminField
        >
      {/snippet}
      {#snippet actions()}<AdminButton variant="primary" type="submit" disabled={busy}
          >{at("ads_apply_filters")}</AdminButton
        ><AdminButton
          disabled={busy}
          onclick={() => {
            start = "";
            end = "";
            periodMode = "events";
            linkFilter = "";
            evidenceFilter = "";
            channelFilter = "";
            currencyFilter = "";
            page = 0;
            void load();
          }}>{at("reset_filters")}</AdminButton
        >{/snippet}
    </AdminListToolbar>
  {/if}
  <div class="ad-export-toolbar">
    <div class="ad-export-actions">
      <AdminSelect
        bind:value={exportKind}
        items={["report", "contacts", "purchases", "matches"].map((value) => ({
          value,
          label: at(`ads_export_${value}`),
        }))}
        ariaLabel={at("ads_export_kind")}
      /><AdminButton disabled={busy} onclick={() => download(exportKind)}
        ><Download size={15} />{at("ads_export")}</AdminButton
      >
    </div>
    <a
      href={`${documentationUrl.replace(/\/$/, "")}/features/advertising/`}
      target="_blank"
      rel="noreferrer">{at("ads_documentation")}</a
    >
  </div>
  {#if error}<p role="alert">{error}</p>
    <AdminButton onclick={() => load()}>{at("retry")}</AdminButton>{/if}
  {#if !data}<AdminEmptyState><span>{busy ? at("loading") : at("ads_empty")}</span></AdminEmptyState
    >
  {:else if tab === "overview"}<AdReportPanel {data} {at} />
  {:else if tab === "links"}<AdLinksPanel {data} {at} {mutate} />
  {:else if tab === "offers"}<AdLinksPanel {data} {at} {mutate} offers />
  {:else if tab === "imports"}<AdImportsPanel {data} {at} {mutate} />
  {:else if tab === "contacts"}
    <AdminSettingsGroup title={at("ads_tab_contacts")} description={at("ads_contacts_hint")}>
      <AdminButton onclick={() => store.loadAdPurchases(data!.campaign)}
        >{at("btn_purchases")}</AdminButton
      >
      <AdminTable layout="fixed"
        ><thead
          ><tr
            ><th>ID</th><th>{at("ads_user")}</th><th>{at("ads_channel")}</th><th
              >{at("ads_evidence")}</th
            ><th>{at("ads_date")}</th><th>{at("ads_registration")}</th><th>UTM</th></tr
          ></thead
        >
        <tbody
          >{#each data.touches as touch (touch.id)}<tr>
              <td data-label="ID">{touch.id}</td><td data-label={at("ads_user")}
                ><span
                  >{touch.user_id ??
                    at(
                      "ads_anonymous"
                    )}{#if touch.original_user_id && touch.original_user_id !== touch.user_id}
                    <small>← {touch.original_user_id}</small>{/if}</span
                ></td
              >
              <td data-label={at("ads_channel")}>{at(`ads_${touch.channel}`)}</td><td
                data-label={at("ads_evidence")}>{at(`ads_${touch.evidence}`)}</td
              >
              <td data-label={at("ads_date")}>{adDate(touch.occurred_at)}</td><td
                data-label={at("ads_registration")}
                >{touch.is_new_user === null || touch.is_new_user === undefined
                  ? "—"
                  : touch.is_new_user
                    ? at("ads_new_user")
                    : at("ads_returning_user")}</td
              ><td class="admin-cell-wrap" data-label="UTM"
                >{Object.entries(touch.utm)
                  .map(([key, value]) => `${key}=${value}`)
                  .join(" · ")}</td
              >
            </tr>{/each}</tbody
        >
      </AdminTable>
      <AdminPagination
        {page}
        pageCount={Math.ceil(data.touch_total / 25)}
        total={data.touch_total}
        pageLabel={at("page_short")}
        ofLabel={at("pagination_of")}
        totalLabel={at("total")}
        prevLabel={at("back")}
        nextLabel={at("next")}
        onPageChange={(value) => {
          page = value;
          void load();
        }}
      />
    </AdminSettingsGroup>
  {:else if tab === "spend"}
    <AdminSettingsGroup title={at("ads_add_spend")} description={at("ads_spend_hint")}
      ><AdminFormGrid>
        <AdminField label={at("ads_amount")}
          ><Input bind:value={amount} type="number" min="0" step="0.01" /></AdminField
        ><AdminField label={at("ads_currency")}
          ><Input bind:value={currency} maxlength={8} /></AdminField
        ><AdminField label={at("ads_date_utc")}
          ><DateInput
            bind:value={spendDate}
            withTime
            ariaLabel={at("ads_date_utc")}
            locale={at("ads_calendar_locale")}
            clearLabel={at("ads_clear_date")}
          /></AdminField
        ><AdminField label={at("ads_note")}><Input bind:value={note} maxlength={500} /></AdminField>
      </AdminFormGrid>
      <AdminCardActions divider={false}>
        <AdminButton
          disabled={busy ||
            !amount ||
            !Number.isFinite(Number(amount)) ||
            Number(amount) < 0 ||
            !spendDate ||
            Boolean(data.archived_at)}
          variant="primary"
          onclick={async () => {
            if (
              await mutate("spend", { amount, currency, occurred_at: `${spendDate}:00Z`, note })
            ) {
              amount = "";
              note = "";
            }
          }}>{at("ads_add_spend")}</AdminButton
        >
      </AdminCardActions></AdminSettingsGroup
    >
    <AdminTable layout="fixed"
      ><thead
        ><tr
          ><th>{at("ads_date")}</th><th>{at("ads_amount")}</th><th>{at("ads_spend_source")}</th><th
            >{at("ads_note")}</th
          ></tr
        ></thead
      ><tbody
        >{#each data.spends as spend (spend.id)}<tr
            ><td data-label={at("ads_date")}>{adDate(spend.occurred_at)}</td><td
              data-label={at("ads_amount")}
              >{adMoney(spend.amount_minor, spend.currency, spend.scale)}</td
            ><td data-label={at("ads_spend_source")}>{at(`ads_${spend.source}`)}</td><td
              data-label={at("ads_note")}>{spend.note}</td
            ></tr
          >{/each}</tbody
      ></AdminTable
    >
  {:else if tab === "audit"}
    <AdminTable layout="fixed"
      ><thead
        ><tr><th>{at("ads_date")}</th><th>{at("ads_action")}</th><th>{at("ads_operator")}</th></tr
        ></thead
      ><tbody
        >{#each data.audit as entry (entry.id)}<tr
            ><td data-label={at("ads_date")}>{adDate(entry.created_at)}</td><td
              data-label={at("ads_action")}
              >{at(`ads_audit_${entry.action.replaceAll(".", "_")}`)}</td
            ><td data-label={at("ads_operator")}>{entry.actor_id}</td></tr
          >{/each}</tbody
      ></AdminTable
    >
  {:else if tab === "settings"}
    <AdminSettingsGroup title={at("ads_settings_general")} description={at("ads_settings_hint")}
      ><AdminFormGrid>
        <AdminField label={at("ads_name")}><Input bind:value={name} maxlength={160} /></AdminField>
        <AdminField label={at("ads_legacy_cost")}
          ><Input type="number" bind:value={cost} min="0" step="0.01" /></AdminField
        >
        <AdminField label={at("ads_currency")}
          ><Input bind:value={reportCurrency} maxlength={8} /></AdminField
        >
        <AdminField label={at("ads_attribution_window")}
          ><Input type="number" bind:value={windowDays} min="1" max="365" /></AdminField
        >
        <AdminField label={at("ads_spend_source")}
          ><AdminSelect
            bind:value={spendSource}
            items={[
              { value: "legacy", label: at("ads_legacy") },
              { value: "manual", label: at("ads_manual") },
              { value: "import", label: at("ads_import") },
            ]}
            ariaLabel={at("ads_spend_source")}
          /></AdminField
        >
        <AdminField label={at("ad_label_advertiser")} hint={at("ad_hint_advertiser")}
          ><Input type="number" bind:value={advertiser} /></AdminField
        >
      </AdminFormGrid>
      <AdminField label={at("ads_description")}
        ><Textarea
          bind:value={description}
          maxlength={2000}
          rows={3}
          ariaLabel={at("ads_description")}
        /></AdminField
      >
      <AdminCardActions divider={false}>
        <AdminButton variant="primary" disabled={busy || resetPending} onclick={saveSettings}
          >{at("save")}</AdminButton
        >
      </AdminCardActions></AdminSettingsGroup
    >
    <AdminCardActions divider={false}>
      <AdminButton
        disabled={busy || resetPending || Boolean(data.archived_at)}
        onclick={() => store.toggleAd(data!.campaign).then(() => load())}
        >{data.campaign.is_active ? at("ads_pause") : at("ads_resume")}</AdminButton
      >
      <AdminButton disabled={busy || resetPending} onclick={() => (resetOpen = true)}
        >{at("ads_reset_legacy")}</AdminButton
      >
      <AdminButton
        variant="dangerSoft"
        disabled={busy || resetPending || Boolean(data.archived_at)}
        onclick={() => (archiveOpen = true)}>{at("ads_archive")}</AdminButton
      >
    </AdminCardActions>
  {/if}
</div>
<Dialog
  open={archiveOpen}
  title={at("ads_archive")}
  description={at("ads_archive_hint")}
  closeLabel={at("close")}
  onclose={() => {
    if (!busy) archiveOpen = false;
  }}
  class="admin-dialog admin-dialog-compact"
>
  <AdminCardActions divider={false}>
    <AdminButton disabled={busy} onclick={() => (archiveOpen = false)}>{at("cancel")}</AdminButton>
    <AdminButton
      variant="danger"
      disabled={busy}
      onclick={async () => {
        if (await mutate("archive")) archiveOpen = false;
      }}>{busy ? at("loading") : at("ads_archive")}</AdminButton
    >
  </AdminCardActions>
</Dialog>

<Dialog
  open={resetOpen}
  title={at("ads_reset_legacy")}
  description={at("ads_reset_legacy_hint")}
  closeLabel={at("close")}
  onclose={() => {
    if (!busy && !resetPending) resetOpen = false;
  }}
  class="admin-dialog admin-dialog-compact"
>
  <AdminCardActions divider={false}>
    <AdminButton disabled={busy || resetPending} onclick={() => (resetOpen = false)}
      >{at("cancel")}</AdminButton
    >
    <AdminButton
      variant="dangerSoft"
      disabled={busy || resetPending}
      onclick={async () => {
        if (!data || busy || resetPending) return;
        resetPending = true;
        try {
          await store.resetAdStats(data.campaign);
          resetOpen = false;
          await load();
        } catch {
          error = at("ads_load_failed");
        } finally {
          resetPending = false;
        }
      }}>{resetPending ? at("loading") : at("confirm")}</AdminButton
    >
  </AdminCardActions>
</Dialog>

<style>
  .ad-workspace {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  .ad-workspace-header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
  }
  .ad-workspace-title {
    display: grid;
    gap: 3px;
    flex: 1;
    min-width: 180px;
  }
  .ad-workspace-title h2 {
    margin: 0;
    font-size: 20px;
    overflow-wrap: anywhere;
  }
  .ad-workspace-title small {
    color: var(--admin-muted);
    font-size: 12px;
    overflow-wrap: anywhere;
  }
  .ad-export-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .ad-export-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .ad-export-actions :global(.admin-select-trigger) {
    width: min(240px, 100%);
  }
  .ad-export-toolbar a {
    color: var(--admin-muted);
    font-size: 12px;
  }
  :global(.ad-workspace .admin-tabs-list) {
    flex-wrap: wrap;
  }
  @media (max-width: 720px) {
    .ad-workspace-title {
      flex-basis: calc(100% - 150px);
      min-width: 0;
    }
    .ad-export-actions {
      width: 100%;
    }
    .ad-export-actions :global(.admin-select-trigger) {
      flex: 1;
      width: auto;
    }
  }
</style>
