<script lang="ts">
  import { onMount } from "svelte";
  import { getAdsStore } from "$lib/admin/context";
  import {
    AdminButton,
    AdminEmptyState,
    AdminField,
    AdminListToolbar,
    AdminPagination,
    AdminSelect,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { RefreshCw } from "$components/ui/icons.js";
  import { unwrap } from "$lib/webapp/publicApi";
  import type { components } from "$lib/api/openapi.generated";
  import { adError, adDate, type Translate } from "./types";
  let { at }: { at: Translate } = $props();
  let pendingTouch = $state<components["schemas"]["AdTouchOut"] | null>(null);
  const store = getAdsStore();
  let touches = $state.raw<components["schemas"]["AdTouchOut"][]>([]);
  let campaign = $state("");
  let page = $state(0),
    total = $state(0);
  let choices = $state<Record<string, string>>({});
  let error = $state("");
  let busy = $state(false);
  const items = $derived(Object.entries(choices).map(([value, label]) => ({ value, label })));
  async function load() {
    busy = true;
    error = "";
    try {
      const response = await store.request(`/admin/ads/unassigned?page=${page}&page_size=25`);
      if (response.ok === true) {
        const value = unwrap(response);
        touches = value.touches;
        total = value.total;
        choices = value.campaigns || {};
      } else error = at("ads_load_failed");
    } catch {
      error = at("ads_load_failed");
    } finally {
      busy = false;
    }
  }
  async function assign(utm: Record<string, string>) {
    busy = true;
    try {
      const response = await store.request("/admin/ads/unassigned/assign", {
        method: "POST",
        body: JSON.stringify({ campaign_id: Number(campaign), utm }),
      });
      if (response.ok === true) {
        pendingTouch = null;
        await load();
      } else error = at("ads_action_failed", { reason: adError(response) });
    } catch {
      error = at("ads_load_failed");
    } finally {
      busy = false;
    }
  }
  onMount(() => {
    void load();
  });
</script>

<section class="ad-unassigned" aria-busy={busy}>
  <div class="ad-unassigned-copy">
    <h2>{at("ads_unassigned")}</h2>
    <p class="admin-muted">{at("ads_unassigned_hint")}</p>
  </div>
  <AdminListToolbar {total} totalLabel={at("total")} columns={1}>
    {#snippet filters()}<AdminField label={at("ads_assign_campaign")}
        ><AdminSelect
          bind:value={campaign}
          {items}
          placeholder={at("ads_select_campaign")}
          ariaLabel={at("ads_assign_campaign")}
          disabled={busy}
        /></AdminField
      >{/snippet}
    {#snippet actions()}<AdminButton variant="ghost" disabled={busy} onclick={load}
        ><RefreshCw size={15} />{at("refresh")}</AdminButton
      >{/snippet}
    {#snippet footer()}<small class="admin-muted">{at("ads_unassigned_rule_hint")}</small>{/snippet}
  </AdminListToolbar>
  {#if error}<p role="alert">{error}</p>{/if}
  {#if !touches.length}<AdminEmptyState tone="card"
      >{busy ? at("loading") : at("ads_unassigned_empty")}</AdminEmptyState
    >
  {:else}<AdminTable layout="fixed">
      <colgroup
        ><col style="width:20%" /><col style="width:16%" /><col style="width:44%" /><col
          style="width:20%"
        /></colgroup
      >
      <thead
        ><tr
          ><th>{at("ads_date")}</th><th>{at("ads_user")}</th><th>UTM</th><th>{at("actions")}</th
          ></tr
        ></thead
      >
      <tbody
        >{#each touches as touch (touch.id)}<tr>
            <td data-label={at("ads_date")}>{adDate(touch.occurred_at)}</td>
            <td data-label={at("ads_user")}>{touch.user_id ?? at("ads_anonymous")}</td>
            <td class="admin-cell-wrap" data-label="UTM"
              ><div class="ad-unassigned-utm">
                {#each Object.entries(touch.utm) as [key, value] (key)}<span
                    ><strong>{key}</strong> = {value}</span
                  >{/each}
              </div></td
            >
            <td class="admin-cell-actions" data-label={at("actions")}
              ><AdminButton
                size="sm"
                disabled={!campaign || busy || !Object.keys(touch.utm).length}
                onclick={() => {
                  pendingTouch = touch;
                }}>{at("ads_assign_utm")}</AdminButton
              ></td
            >
          </tr>{/each}</tbody
      >
    </AdminTable>{/if}
  {#if total > 25}<AdminPagination
      {page}
      pageCount={Math.ceil(total / 25)}
      {total}
      pageLabel={at("page_short")}
      ofLabel={at("pagination_of")}
      totalLabel={at("total")}
      prevLabel={at("back")}
      nextLabel={at("next")}
      onPageChange={(value) => {
        page = value;
        void load();
      }}
    />{/if}
</section>
<Dialog
  open={pendingTouch !== null}
  title={at("ads_assign_utm")}
  description={at("ads_unassigned_rule_hint")}
  closeLabel={at("close")}
  class="admin-dialog"
  onclose={() => {
    if (!busy) pendingTouch = null;
  }}
>
  <div class="admin-dialog-content">
    <p>{choices[campaign] || campaign}</p>
    {#if pendingTouch}<div class="ad-unassigned-utm">
        {#each Object.entries(pendingTouch.utm) as [key, value] (key)}<span
            ><strong>{key}</strong> = {value}</span
          >{/each}
      </div>{/if}
    <div class="admin-dialog-actions">
      <AdminButton
        disabled={busy}
        onclick={() => {
          pendingTouch = null;
        }}>{at("btn_cancel")}</AdminButton
      ><AdminButton
        variant="primary"
        disabled={busy || !campaign}
        onclick={() => {
          if (pendingTouch) void assign(pendingTouch.utm);
        }}>{at("confirm")}</AdminButton
      >
    </div>
  </div>
</Dialog>

<style>
  .ad-unassigned {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  .ad-unassigned-copy {
    display: grid;
    gap: 6px;
  }
  .ad-unassigned-copy h2 {
    margin: 0;
    font-size: 18px;
  }
  .ad-unassigned-copy p {
    margin: 0;
    font-size: 13px;
  }
  .ad-unassigned-utm {
    display: grid;
    gap: 4px;
    font-size: 12px;
    overflow-wrap: anywhere;
  }
</style>
