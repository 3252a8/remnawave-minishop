<script lang="ts">
  import { onMount } from "svelte";
  import { getAdsStore } from "$lib/admin/context";
  import { buildAdvertisingPath, buildAdvertisingExportPath, unwrap } from "$lib/webapp/publicApi";
  import { Input } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminButton,
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
  <div class="ad-toolbar">
    <AdminButton onclick={onback}>← {at("ads_campaigns")}</AdminButton>
    <h2>{data?.name || at("ads_campaign")}</h2>
    {#if data?.archived_at}<span>{at("ads_archived")}</span>{/if}<AdminButton
      disabled={busy}
      onclick={() => load()}>{at("refresh")}</AdminButton
    >
  </div>
  <div class="ad-filters">
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
    <AdminField label={at("ads_period_start")}><Input type="date" bind:value={start} /></AdminField>
    <AdminField label={at("ads_period_end")}><Input type="date" bind:value={end} /></AdminField>
    <AdminButton
      disabled={busy}
      onclick={() => {
        page = 0;
        void load();
      }}>{at("ads_apply_filters")}</AdminButton
    >
  </div>
  <div class="ad-toolbar">
    {#each ["report", "contacts", "purchases", "matches"] as kind}
      <AdminButton disabled={busy} onclick={() => download(kind)}
        >{at(`ads_export_${kind}`)}</AdminButton
      >
    {/each}
    <a
      href={`${documentationUrl.replace(/\/$/, "")}/features/advertising/`}
      target="_blank"
      rel="noreferrer">{at("ads_documentation")}</a
    >
  </div>
  <div class="ad-filters">
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
      ><Input bind:value={currencyFilter} placeholder="RUB / XTR / TON" maxlength={8} /></AdminField
    >
    <AdminButton
      disabled={busy}
      onclick={() => {
        page = 0;
        void load();
      }}>{at("ads_apply_filters")}</AdminButton
    >
  </div>
  <nav class="ad-tabs" aria-label={at("ads_campaign_sections")}>
    {#each tabs as item}<AdminButton
        variant={tab === item ? "primary" : "default"}
        aria-pressed={tab === item}
        onclick={() => {
          tab = item;
        }}>{at(`ads_tab_${item}`)}</AdminButton
      >{/each}
  </nav>
  {#if error}<p role="alert">{error}</p>
    <AdminButton onclick={() => load()}>{at("retry")}</AdminButton>{/if}
  {#if !data}<AdminEmptyState><span>{busy ? at("loading") : at("ads_empty")}</span></AdminEmptyState
    >
  {:else if tab === "overview"}<AdReportPanel {data} {at} />
  {:else if tab === "links"}<AdLinksPanel {data} {at} {mutate} />
  {:else if tab === "offers"}<AdLinksPanel {data} {at} {mutate} offers />
  {:else if tab === "imports"}<AdImportsPanel {data} {at} {mutate} />
  {:else if tab === "contacts"}
    <p class="admin-muted">{at("ads_contacts_hint")}</p>
    <AdminButton onclick={() => store.loadAdPurchases(data!.campaign)}
      >{at("btn_purchases")}</AdminButton
    >
    <AdminTable
      ><thead
        ><tr
          ><th>ID</th><th>{at("ads_user")}</th><th>{at("ads_channel")}</th><th
            >{at("ads_evidence")}</th
          ><th>{at("ads_date")}</th><th>{at("ads_registration")}</th><th>UTM</th></tr
        ></thead
      >
      <tbody
        >{#each data.touches as touch}<tr>
            <td data-label="ID">{touch.id}</td><td data-label={at("ads_user")}
              >{touch.user_id ??
                at(
                  "ads_anonymous"
                )}{#if touch.original_user_id && touch.original_user_id !== touch.user_id}
                <small>← {touch.original_user_id}</small>{/if}</td
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
            ><td data-label="UTM"
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
  {:else if tab === "spend"}
    <p class="admin-muted">{at("ads_spend_hint")}</p>
    <div class="ad-form-grid admin-form">
      <AdminField label={at("ads_amount")}
        ><Input bind:value={amount} type="number" min="0" step="0.01" /></AdminField
      ><AdminField label={at("ads_currency")}
        ><Input bind:value={currency} maxlength={8} /></AdminField
      ><AdminField label={at("ads_date_utc")}
        ><Input bind:value={spendDate} type="datetime-local" /></AdminField
      ><AdminField label={at("ads_note")}><Input bind:value={note} maxlength={500} /></AdminField
      ><AdminButton
        disabled={!amount || Boolean(data.archived_at)}
        variant="primary"
        onclick={async () => {
          if (await mutate("spend", { amount, currency, occurred_at: `${spendDate}:00Z`, note })) {
            amount = "";
            note = "";
          }
        }}>{at("ads_add_spend")}</AdminButton
      >
    </div>
    <AdminTable
      ><thead
        ><tr
          ><th>{at("ads_date")}</th><th>{at("ads_amount")}</th><th>{at("ads_spend_source")}</th><th
            >{at("ads_note")}</th
          ></tr
        ></thead
      ><tbody
        >{#each data.spends as spend}<tr
            ><td>{adDate(spend.occurred_at)}</td><td
              >{adMoney(spend.amount_minor, spend.currency, spend.scale)}</td
            ><td>{at(`ads_${spend.source}`)}</td><td>{spend.note}</td></tr
          >{/each}</tbody
      ></AdminTable
    >
  {:else if tab === "audit"}
    <AdminTable
      ><thead
        ><tr><th>{at("ads_date")}</th><th>{at("ads_action")}</th><th>{at("ads_operator")}</th></tr
        ></thead
      ><tbody
        >{#each data.audit as entry}<tr
            ><td>{adDate(entry.created_at)}</td><td
              >{at(`ads_audit_${entry.action.replaceAll(".", "_")}`)}</td
            ><td>{entry.actor_id}</td></tr
          >{/each}</tbody
      ></AdminTable
    >
  {:else if tab === "settings"}
    <AdminButton
      disabled={busy}
      onclick={() => {
        resetOpen = true;
      }}>{at("ads_reset_legacy")}</AdminButton
    >
    <div class="admin-form ad-form-grid">
      <AdminField label={at("ads_name")}><Input bind:value={name} maxlength={160} /></AdminField>
      <AdminField label={at("ads_description")}
        ><Input bind:value={description} maxlength={2000} /></AdminField
      >
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
    </div>
    <p class="admin-muted">{at("ads_settings_hint")}</p>
    <div class="ad-toolbar">
      <AdminButton variant="primary" disabled={busy} onclick={saveSettings}
        >{at("save")}</AdminButton
      ><AdminButton
        disabled={busy || Boolean(data.archived_at)}
        onclick={() => store.toggleAd(data!.campaign).then(() => load())}
        >{data.campaign.is_active ? at("ads_pause") : at("ads_resume")}</AdminButton
      ><AdminButton
        variant="dangerSoft"
        disabled={Boolean(data.archived_at)}
        onclick={() => {
          archiveOpen = true;
        }}>{at("ads_archive")}</AdminButton
      >
    </div>
  {/if}
</div>
<Dialog
  open={archiveOpen}
  title={at("ads_archive")}
  closeLabel={at("close")}
  onclose={() => {
    archiveOpen = false;
  }}
  class="admin-dialog admin-dialog-compact"
  ><p>{at("ads_archive_hint")}</p>
  <AdminButton
    variant="danger"
    onclick={async () => {
      if (await mutate("archive")) archiveOpen = false;
    }}>{at("ads_archive")}</AdminButton
  ></Dialog
>

<Dialog
  open={resetOpen}
  title={at("ads_reset_legacy")}
  closeLabel={at("close")}
  onclose={() => {
    resetOpen = false;
  }}
>
  <p>{at("ads_reset_legacy_hint")}</p>
  <AdminButton
    disabled={busy}
    onclick={async () => {
      if (data) {
        await store.resetAdStats(data.campaign);
        resetOpen = false;
        await load();
      }
    }}>{at("confirm")}</AdminButton
  >
</Dialog>

<style>
  .ad-workspace {
    display: grid;
    gap: 20px;
  }
  .ad-toolbar,
  .ad-tabs {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
  }
  .ad-toolbar h2 {
    margin: 0;
    flex: 1;
  }
  .ad-filters,
  .ad-form-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    align-items: end;
    gap: 12px;
  }
</style>
