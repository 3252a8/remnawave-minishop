<script lang="ts">
  import { Input, FileInput, Textarea } from "$components/ui/index.js";
  import { csvHeader } from "./csvHeader";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminButton,
    AdminField,
    AdminSelect,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import { buildAdvertisingPath, unwrap } from "$lib/webapp/publicApi";
  import { getAdsStore } from "$lib/admin/context";
  import type { components } from "$lib/api/openapi.generated";
  import { adError, adDate, type AdDetail, type Translate, type Mutate } from "./types";
  let { data, at, mutate }: { data: AdDetail; at: Translate; mutate: Mutate } = $props();
  const store = getAdsStore();
  let csv = $state("");
  let account = $state("");
  let timezone = $state("Europe/Moscow");
  let currency = $state("RUB");
  let delimiter = $state(",");
  let granularity = $state("daily");
  let replaceMode = $state("keep");
  let columns = $state<Record<string, string>>({});
  let preview = $state.raw<components["schemas"]["AdImportPreviewOut"] | null>(null);
  let busy = $state(false);
  let error = $state("");
  let botId = $state("");
  let windowSeconds = $state("30");
  let revertId = $state("");
  const fields = [
    "start",
    "end",
    "advertisement",
    "impressions",
    "clicks",
    "starts",
    "cost",
    "currency",
  ];
  const headers = $derived(csvHeader(csv, delimiter));
  const columnItems = $derived([
    { value: "", label: at("ads_column_skip") },
    ...headers.map((value) => ({ value, label: value })),
  ]);
  async function chooseFile(event: Event) {
    const file = (event.currentTarget as HTMLInputElement).files?.[0];
    if (!file) return;
    if (file.size > 1_048_576) {
      error = at("ads_csv_limit");
      return;
    }
    csv = await file.text();
    preview = null;
    columns = {};
  }
  async function prepare() {
    busy = true;
    error = "";
    preview = null;
    try {
      const result = await store.request(buildAdvertisingPath("preview", data.campaign.id), {
        method: "POST",
        body: JSON.stringify({
          csv,
          account,
          timezone,
          currency,
          delimiter,
          granularity,
          mapping: columns,
        }),
      });
      if (result.ok === true) preview = unwrap(result);
      else error = at("ads_action_failed", { reason: adError(result) });
    } catch {
      error = at("ads_load_failed");
    } finally {
      busy = false;
    }
  }
  async function confirm() {
    if (
      preview &&
      (await mutate("confirm", { replace: replaceMode === "replace" }, preview.batch.id))
    )
      preview = null;
  }
</script>

<p class="admin-muted">{at("ads_import_hint")}</p>
<p class="admin-muted">{at("ads_csv_limit")}</p>
<div class="admin-form ad-form-grid">
  <AdminField label={at("ads_csv_file")}
    ><FileInput
      aria-label={at("ads_csv_file")}
      accept=".csv,text/csv"
      onchange={chooseFile}
    /></AdminField
  >
  <AdminField label={at("ads_import_account")}
    ><Input bind:value={account} maxlength={128} /></AdminField
  >
  <AdminField label={at("ads_timezone")}><Input bind:value={timezone} /></AdminField>
  <AdminField label={at("ads_currency")}><Input bind:value={currency} maxlength={8} /></AdminField>
  <AdminField label={at("ads_delimiter")}
    ><AdminSelect
      bind:value={delimiter}
      items={[
        { value: ",", label: at("ads_comma") },
        { value: ";", label: at("ads_semicolon") },
        { value: "\t", label: at("ads_tab") },
      ]}
      ariaLabel={at("ads_delimiter")}
    /></AdminField
  >
  <AdminField label={at("ads_granularity")}
    ><AdminSelect
      bind:value={granularity}
      items={[
        { value: "daily", label: at("ads_daily") },
        { value: "minute", label: at("ads_minute") },
        { value: "interval", label: at("ads_interval") },
        { value: "cumulative", label: at("ads_cumulative") },
        { value: "event", label: at("ads_event") },
      ]}
      ariaLabel={at("ads_granularity")}
    /></AdminField
  >
</div>
<AdminField label={at("ads_csv_text")}
  ><Textarea
    class="input ad-csv-input"
    bind:value={csv}
    ariaLabel={at("ads_csv_text")}
    rows={5}
    oninput={() => {
      preview = null;
    }}
    placeholder="date,ad,impressions,clicks,starts,cost,currency"
  ></Textarea></AdminField
>
<div class="admin-form ad-form-grid">
  {#each fields as field}<AdminField label={at(`ads_column_${field}`)}
      ><AdminSelect
        value={columns[field] || ""}
        items={columnItems}
        ariaLabel={at(`ads_column_${field}`)}
        onValueChange={(value) => {
          columns = { ...columns, [field]: value };
          preview = null;
        }}
      /></AdminField
    >{/each}
</div>
{#if error}<p role="alert">{error}</p>{/if}
<AdminButton
  variant="primary"
  disabled={busy || !csv || !account || !columns.start || !columns.advertisement}
  onclick={prepare}>{busy ? at("loading") : at("ads_preview_import")}</AdminButton
>
{#if preview}
  <h3>{at("ads_import_preview", { count: preview.batch.rows })}</h3>
  <p class="admin-muted">{at("ads_preview_limit")}</p>
  <AdminTable
    ><thead
      ><tr
        ><th>{at("ads_column_start")}</th><th>{at("ads_column_advertisement")}</th><th
          >{at("ads_impressions")}</th
        ><th>{at("ads_clicks")}</th><th>{at("ads_starts")}</th><th>{at("ads_spend")}</th></tr
      ></thead
    >
    <tbody
      >{#each preview.preview.slice(0, 20) as row}<tr
          ><td>{String(row.interval_start || "")}</td><td>{String(row.advertisement || "")}</td><td
            >{Array.isArray(row.available_metrics) && row.available_metrics.includes("impressions")
              ? String(row.impressions ?? 0)
              : "—"}</td
          ><td
            >{Array.isArray(row.available_metrics) && row.available_metrics.includes("clicks")
              ? String(row.clicks ?? 0)
              : "—"}</td
          ><td
            >{Array.isArray(row.available_metrics) && row.available_metrics.includes("starts")
              ? String(row.starts ?? 0)
              : "—"}</td
          ><td
            >{row.cost_minor == null ? "—" : String(row.cost_minor)}
            {String(row.currency || "")} · {at("ads_minor_units")}</td
          ></tr
        >{/each}</tbody
    >
  </AdminTable>
  <p class="admin-muted">{at("ads_import_replace_hint")}</p>
  <AdminSelect
    bind:value={replaceMode}
    items={[
      { value: "keep", label: at("ads_keep_imports") },
      { value: "replace", label: at("ads_replace_imports") },
    ]}
    ariaLabel={at("ads_import_revision")}
  />
  <AdminButton variant="primary" onclick={confirm}>{at("ads_confirm_import")}</AdminButton>
{/if}
<h3>{at("ads_import_history")}</h3>
<AdminTable
  ><thead
    ><tr
      ><th>{at("ads_import_account")}</th><th>{at("ads_date")}</th><th>{at("ads_rows")}</th><th
        >{at("ads_status")}</th
      ><th>{at("actions")}</th></tr
    ></thead
  >
  <tbody
    >{#each data.imports as batch}<tr
        ><td>{batch.account}</td><td>{adDate(batch.created_at)}</td><td
          >{batch.rows} · {at(`ads_${batch.granularity}`)}</td
        ><td>{at(`ads_${batch.status}`)}</td><td
          >{#if batch.status === "confirmed"}<AdminButton
              variant="dangerSoft"
              onclick={() => {
                revertId = batch.id;
              }}>{at("ads_revert_import")}</AdminButton
            >{/if}{#if batch.granularity === "event" && batch.status === "confirmed"}<AdminButton
              disabled={!botId}
              onclick={() =>
                mutate(
                  "candidates",
                  { bot_id: botId, window_seconds: Number(windowSeconds) },
                  batch.id
                )}>{at("ads_find_candidates")}</AdminButton
            >{/if}</td
        ></tr
      >{/each}</tbody
  >
</AdminTable>
<h3>{at("ads_matching")}</h3>
<p class="admin-muted">{at("ads_matching_hint")}</p>
<div class="ad-form-grid">
  <AdminField label={at("ads_bot_id")}><Input bind:value={botId} /></AdminField><AdminField
    label={at("ads_match_window")}
    ><Input type="number" min="1" max="3600" bind:value={windowSeconds} /></AdminField
  >
</div>
<AdminTable
  ><thead
    ><tr
      ><th>ID</th><th>{at("ads_contact")}</th><th>{at("ads_delta_seconds")}</th><th
        >{at("ads_status")}</th
      ><th>{at("ads_reason")}</th><th>{at("actions")}</th></tr
    ></thead
  >
  <tbody
    >{#each data.candidates as candidate}<tr
        ><td>{candidate.id}</td><td>{candidate.touchpoint_id || "—"}</td><td
          >{candidate.delta_seconds ?? "—"}</td
        ><td>{at(`ads_${candidate.status}`)}</td><td
          >{at(`ads_match_${candidate.reason}`)} &middot; &plusmn;{candidate.window_seconds}s
          &middot; {candidate.bot_id}</td
        ><td
          >{#if candidate.touchpoint_id && ["candidate", "ambiguous"].includes(candidate.status)}<AdminButton
              onclick={() => mutate("decide", { status: "confirmed_by_operator" }, candidate.id)}
              >{at("ads_confirm_candidate")}</AdminButton
            ><AdminButton onclick={() => mutate("decide", { status: "rejected" }, candidate.id)}
              >{at("ads_reject_candidate")}</AdminButton
            >{/if}</td
        ></tr
      >{/each}</tbody
  >
</AdminTable>
<Dialog
  open={Boolean(revertId)}
  title={at("ads_revert_import")}
  closeLabel={at("close")}
  onclose={() => {
    revertId = "";
  }}
  class="admin-dialog admin-dialog-compact"
>
  <p>{at("ads_revert_hint")}</p>
  <AdminButton
    variant="danger"
    onclick={async () => {
      if (await mutate("revert", {}, revertId)) revertId = "";
    }}>{at("ads_revert_import")}</AdminButton
  >
</Dialog>

<style>
  .ad-form-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 12px;
    margin: 16px 0;
  }
</style>
