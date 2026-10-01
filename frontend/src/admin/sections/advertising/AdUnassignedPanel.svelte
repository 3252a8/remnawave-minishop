<script lang="ts">
  import { onMount } from "svelte";
  import { getAdsStore } from "$lib/admin/context";
  import {
    AdminButton,
    AdminPagination,
    AdminSelect,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import { unwrap } from "$lib/webapp/publicApi";
  import type { components } from "$lib/api/openapi.generated";
  import { adError, adDate, type Translate } from "./types";
  let { at, onback }: { at: Translate; onback: () => void } = $props();
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
      if (response.ok === true) await load();
      else error = at("ads_action_failed", { reason: adError(response) });
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

<AdminButton onclick={onback}>← {at("ads_campaigns")}</AdminButton>
<h2>{at("ads_unassigned")}</h2>
<p class="admin-muted">{at("ads_unassigned_hint")}</p>
<AdminSelect bind:value={campaign} {items} ariaLabel={at("ads_campaign")} />
{#if error}<p role="alert">{error}</p>{/if}
<AdminButton disabled={busy} onclick={load}>{at("refresh")}</AdminButton>
<AdminTable
  ><thead
    ><tr><th>{at("ads_date")}</th><th>{at("ads_user")}</th><th>UTM</th><th>{at("actions")}</th></tr
    ></thead
  ><tbody
    >{#each touches as touch}<tr
        ><td>{adDate(touch.occurred_at)}</td><td>{touch.user_id ?? at("ads_anonymous")}</td><td
          >{Object.entries(touch.utm)
            .map(([key, value]) => `${key}=${value}`)
            .join(" · ")}</td
        ><td
          ><AdminButton
            disabled={!campaign || busy || !Object.keys(touch.utm).length}
            onclick={() => assign(touch.utm)}>{at("ads_assign_utm")}</AdminButton
          ></td
        ></tr
      >{/each}</tbody
  ></AdminTable
>

<AdminPagination
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
/>
