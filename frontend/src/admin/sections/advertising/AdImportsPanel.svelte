<script lang="ts">
  import { Input, FileInput, Textarea } from "$components/ui/index.js";
  import { csvHeader } from "./csvHeader";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminCardActions,
    AdminEmptyState,
    AdminFormGrid,
    AdminSettingsGroup,
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

<div class="ad-imports-panel">
  <AdminSettingsGroup title={at("ads_import_settings")} description={at("ads_import_hint")}>
    <AdminField label={at("ads_csv_file")} hint={at("ads_csv_limit")}>
      <FileInput
        buttonLabel={at("ads_choose_file")}
        emptyLabel={at("ads_no_file_selected")}
        aria-label={at("ads_csv_file")}
        accept=".csv,text/csv"
        onchange={chooseFile}
      />
    </AdminField>
    <AdminFormGrid columns={3}>
      <AdminField label={at("ads_import_account")}>
        <Input
          bind:value={account}
          maxlength={128}
          aria-label={at("ads_import_account")}
          oninput={() => (preview = null)}
        />
      </AdminField>
      <AdminField label={at("ads_timezone")}>
        <Input
          bind:value={timezone}
          aria-label={at("ads_timezone")}
          oninput={() => (preview = null)}
        />
      </AdminField>
      <AdminField label={at("ads_currency")}>
        <Input
          bind:value={currency}
          maxlength={8}
          aria-label={at("ads_currency")}
          oninput={() => (preview = null)}
        />
      </AdminField>
      <AdminField label={at("ads_delimiter")}>
        <AdminSelect
          bind:value={delimiter}
          items={[
            { value: ",", label: at("ads_comma") },
            { value: ";", label: at("ads_semicolon") },
            { value: "\t", label: at("ads_tab") },
          ]}
          ariaLabel={at("ads_delimiter")}
          onValueChange={() => {
            preview = null;
            columns = {};
          }}
        />
      </AdminField>
      <AdminField label={at("ads_granularity")}>
        <AdminSelect
          bind:value={granularity}
          items={[
            { value: "daily", label: at("ads_daily") },
            { value: "minute", label: at("ads_minute") },
            { value: "interval", label: at("ads_interval") },
            { value: "cumulative", label: at("ads_cumulative") },
            { value: "event", label: at("ads_event") },
          ]}
          ariaLabel={at("ads_granularity")}
          onValueChange={() => (preview = null)}
        />
      </AdminField>
    </AdminFormGrid>
    <AdminField label={at("ads_csv_text")}>
      <Textarea
        bind:value={csv}
        ariaLabel={at("ads_csv_text")}
        rows={5}
        oninput={() => (preview = null)}
        placeholder="date,ad,impressions,clicks,starts,cost,currency"
      />
    </AdminField>
  </AdminSettingsGroup>

  <AdminSettingsGroup title={at("ads_import_mapping")}>
    <AdminFormGrid columns={4}>
      {#each fields as field (field)}
        <AdminField label={at(`ads_column_${field}`)}>
          <AdminSelect
            value={columns[field] || ""}
            items={columnItems}
            disabled={!headers.length}
            ariaLabel={at(`ads_column_${field}`)}
            onValueChange={(value) => {
              columns = { ...columns, [field]: value };
              preview = null;
            }}
          />
        </AdminField>
      {/each}
    </AdminFormGrid>
    {#if error}<p class="ad-panel-note" role="alert">{error}</p>{/if}
    <AdminCardActions divider={false}>
      <AdminButton
        variant="primary"
        disabled={busy || !csv || !account || !columns.start || !columns.advertisement}
        onclick={prepare}>{busy ? at("loading") : at("ads_preview_import")}</AdminButton
      >
    </AdminCardActions>
  </AdminSettingsGroup>

  {#if preview}
    <AdminSettingsGroup
      title={at("ads_import_preview", { count: preview.batch.rows })}
      description={at("ads_preview_limit")}
    >
      <AdminTable
        layout="fixed"
        class="admin-table-compact"
        aria-label={at("ads_import_preview", { count: preview.batch.rows })}
      >
        <thead>
          <tr>
            <th>{at("ads_column_advertisement")}</th>
            <th>{at("ads_column_start")}</th>
            <th>{at("ads_impressions")}</th>
            <th>{at("ads_clicks")}</th>
            <th>{at("ads_starts")}</th>
            <th>{at("ads_spend")}</th>
          </tr>
        </thead>
        <tbody>
          {#each preview.preview.slice(0, 20) as row, index (index)}
            <tr>
              <td class="admin-cell-primary" data-label={at("ads_column_advertisement")}
                >{String(row.advertisement || "")}</td
              >
              <td data-label={at("ads_column_start")}>{String(row.interval_start || "")}</td>
              <td data-label={at("ads_impressions")}>
                {Array.isArray(row.available_metrics) &&
                row.available_metrics.includes("impressions")
                  ? String(row.impressions ?? 0)
                  : "—"}
              </td>
              <td data-label={at("ads_clicks")}>
                {Array.isArray(row.available_metrics) && row.available_metrics.includes("clicks")
                  ? String(row.clicks ?? 0)
                  : "—"}
              </td>
              <td data-label={at("ads_starts")}>
                {Array.isArray(row.available_metrics) && row.available_metrics.includes("starts")
                  ? String(row.starts ?? 0)
                  : "—"}
              </td>
              <td data-label={at("ads_spend")}>
                <div class="ad-cell-stack">
                  <span
                    >{row.cost_minor == null ? "—" : String(row.cost_minor)}
                    {String(row.currency || "")}</span
                  >
                  <small class="admin-muted">{at("ads_minor_units")}</small>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </AdminTable>
      <AdminField label={at("ads_import_revision")} hint={at("ads_import_replace_hint")}>
        <AdminSelect
          bind:value={replaceMode}
          items={[
            { value: "keep", label: at("ads_keep_imports") },
            { value: "replace", label: at("ads_replace_imports") },
          ]}
          ariaLabel={at("ads_import_revision")}
        />
      </AdminField>
      <AdminCardActions divider={false}>
        <AdminButton variant="primary" onclick={confirm}>{at("ads_confirm_import")}</AdminButton>
      </AdminCardActions>
    </AdminSettingsGroup>
  {/if}

  <AdminSettingsGroup title={at("ads_import_history")}>
    {#if data.imports.length}
      <AdminTable layout="fixed" class="admin-table-compact" aria-label={at("ads_import_history")}>
        <thead>
          <tr>
            <th>{at("ads_import_account")}</th>
            <th>{at("ads_date")}</th>
            <th>{at("ads_rows")}</th>
            <th>{at("ads_status")}</th>
            <th>{at("actions")}</th>
          </tr>
        </thead>
        <tbody>
          {#each data.imports as batch (batch.id)}
            <tr>
              <td class="admin-cell-primary" data-label={at("ads_import_account")}
                >{batch.account}</td
              >
              <td data-label={at("ads_date")}>{adDate(batch.created_at)}</td>
              <td data-label={at("ads_rows")}>
                <div class="ad-cell-stack">
                  <strong>{batch.rows}</strong><small class="admin-muted"
                    >{at(`ads_${batch.granularity}`)}</small
                  >
                </div>
              </td>
              <td data-label={at("ads_status")}>
                <AdminBadge
                  variant={batch.status === "confirmed"
                    ? "success"
                    : batch.status === "preview"
                      ? "warning"
                      : "muted"}
                >
                  {at(`ads_${batch.status}`)}
                </AdminBadge>
              </td>
              <td class="admin-cell-actions" data-label={at("actions")}>
                <div class="ad-row-actions">
                  {#if batch.status === "confirmed"}
                    <AdminButton
                      size="sm"
                      variant="dangerSoft"
                      onclick={() => (revertId = batch.id)}>{at("ads_revert_import")}</AdminButton
                    >
                  {/if}
                  {#if batch.granularity === "event" && batch.status === "confirmed"}
                    <AdminButton
                      size="sm"
                      disabled={!botId}
                      onclick={() =>
                        mutate(
                          "candidates",
                          { bot_id: botId, window_seconds: Number(windowSeconds) },
                          batch.id
                        )}>{at("ads_find_candidates")}</AdminButton
                    >
                  {/if}
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </AdminTable>
    {:else}
      <AdminEmptyState>{at("ads_imports_empty")}</AdminEmptyState>
    {/if}
  </AdminSettingsGroup>

  <AdminSettingsGroup title={at("ads_matching")} description={at("ads_matching_hint")}>
    <AdminFormGrid columns={2}>
      <AdminField label={at("ads_bot_id")}
        ><Input bind:value={botId} aria-label={at("ads_bot_id")} /></AdminField
      >
      <AdminField label={at("ads_match_window")}>
        <Input
          type="number"
          min="1"
          max="3600"
          bind:value={windowSeconds}
          aria-label={at("ads_match_window")}
        />
      </AdminField>
    </AdminFormGrid>
    {#if data.candidates.length}
      <AdminTable layout="fixed" class="admin-table-compact" aria-label={at("ads_matching")}>
        <thead>
          <tr>
            <th>{at("id")}</th>
            <th>{at("ads_contact")}</th>
            <th>{at("ads_delta_seconds")}</th>
            <th>{at("ads_status")}</th>
            <th>{at("ads_reason")}</th>
            <th>{at("actions")}</th>
          </tr>
        </thead>
        <tbody>
          {#each data.candidates as candidate (candidate.id)}
            <tr>
              <td class="admin-cell-primary" data-label={at("id")}>{candidate.id}</td>
              <td data-label={at("ads_contact")}>{candidate.touchpoint_id || "—"}</td>
              <td data-label={at("ads_delta_seconds")}>{candidate.delta_seconds ?? "—"}</td>
              <td data-label={at("ads_status")}>
                <AdminBadge
                  variant={candidate.status === "confirmed_by_operator"
                    ? "success"
                    : candidate.status === "ambiguous"
                      ? "warning"
                      : "muted"}
                >
                  {at(`ads_${candidate.status}`)}
                </AdminBadge>
              </td>
              <td data-label={at("ads_reason")}>
                <div class="ad-cell-stack">
                  <span>{at(`ads_match_${candidate.reason}`)}</span>
                  <small class="admin-muted"
                    >±{candidate.window_seconds}s · {candidate.bot_id}</small
                  >
                </div>
              </td>
              <td class="admin-cell-actions" data-label={at("actions")}>
                {#if candidate.touchpoint_id && ["candidate", "ambiguous"].includes(candidate.status)}
                  <div class="ad-row-actions">
                    <AdminButton
                      size="sm"
                      onclick={() =>
                        mutate("decide", { status: "confirmed_by_operator" }, candidate.id)}
                      >{at("ads_confirm_candidate")}</AdminButton
                    >
                    <AdminButton
                      size="sm"
                      onclick={() => mutate("decide", { status: "rejected" }, candidate.id)}
                      >{at("ads_reject_candidate")}</AdminButton
                    >
                  </div>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </AdminTable>
    {:else}
      <AdminEmptyState>{at("ads_candidates_empty")}</AdminEmptyState>
    {/if}
  </AdminSettingsGroup>
</div>

<Dialog
  open={Boolean(revertId)}
  title={at("ads_revert_import")}
  description={at("ads_revert_hint")}
  closeLabel={at("close")}
  onclose={() => (revertId = "")}
  class="admin-dialog admin-dialog-compact"
>
  <AdminCardActions divider={false}>
    <AdminButton onclick={() => (revertId = "")}>{at("cancel")}</AdminButton>
    <AdminButton
      variant="danger"
      onclick={async () => {
        if (await mutate("revert", {}, revertId)) revertId = "";
      }}
    >
      {at("ads_revert_import")}
    </AdminButton>
  </AdminCardActions>
</Dialog>

<style>
  .ad-imports-panel {
    display: grid;
    gap: 18px;
    min-width: 0;
  }
  .ad-panel-note {
    margin: 0;
    line-height: 1.5;
  }
  .ad-cell-stack {
    display: grid;
    gap: 4px;
    min-width: 0;
  }
  .ad-row-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 8px;
    min-width: 0;
  }
  .ad-row-actions :global(.admin-btn) {
    width: 100%;
    max-width: 100%;
    white-space: normal;
  }
  .ad-imports-panel :global(td) {
    font-variant-numeric: tabular-nums;
  }
</style>
