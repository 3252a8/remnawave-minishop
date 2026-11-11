<script lang="ts">
  import { onMount } from "svelte";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import { Checkbox } from "$components/ui/index.js";
  import { getAdminApi, getBroadcastStore } from "$lib/admin/context";
  import { adminErrorMessage } from "$lib/admin/errors";
  import { buildAdminUserBroadcastAudiencesPath, unwrap } from "$lib/webapp/publicApi";
  import type { TranslateFn } from "./userDetailTypes.js";

  let { at, userId }: { at: TranslateFn; userId: number | string } = $props();

  const api = getAdminApi();
  const broadcastStore = getBroadcastStore();
  const path = $derived(buildAdminUserBroadcastAudiencesPath(userId));
  let targets = $state<string[] | null>(null);
  let excluded = $state<string[]>([]);
  let busy = $state(false);
  let error = $state("");
  const rows = $derived([...new Set([...(targets || []), ...excluded])]);
  type Action = "exclude" | "include" | "exclude_all" | "reset";

  function audienceLabel(target: string): string {
    const option = broadcastStore.BROADCAST_TARGET_OPTIONS.find((entry) => entry.value === target);
    if (option) return option.label;
    return target === "without_required_channel"
      ? at(
          "broadcast_target_without_required_channel",
          {},
          "Not subscribed to the required group or channel"
        )
      : target;
  }

  async function load(): Promise<void> {
    busy = true;
    error = "";
    try {
      const response = await api(path);
      if (!response?.ok) {
        error = adminErrorMessage(response, at);
        return;
      }
      const result = unwrap(response);
      targets = result.targets;
      excluded = result.excluded;
    } catch {
      error = at("user_broadcast_audiences_load_error", {}, "Could not load broadcast groups");
    } finally {
      busy = false;
    }
  }

  async function change(action: Action, target?: string): Promise<void> {
    if (busy) return;
    busy = true;
    error = "";
    try {
      const response = await api(path, {
        method: "PATCH",
        body: JSON.stringify({ action, target }),
      });
      if (!response?.ok) {
        error = adminErrorMessage(response, at);
        return;
      }
      excluded = unwrap(response).excluded;
      void broadcastStore.loadCounts({ force: true });
    } catch {
      error = at("user_broadcast_audiences_save_error", {}, "Could not save broadcast groups");
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    void broadcastStore.loadCounts();
    void load();
  });
</script>

<div class="broadcast-audience-preferences">
  <h4>{at("user_broadcast_audiences_title", {}, "Broadcast groups")}</h4>
  <small
    >{at(
      "user_broadcast_audiences_hint",
      {},
      "Clear a group to exclude this user from it. Other selected groups can still include them."
    )}</small
  >
  {#if error}
    <small class="admin-field-error" role="alert">{error}</small>
  {/if}
  {#if targets === null}
    {#if busy}
      <small role="status">{at("loading", {}, "Loading")}</small>
    {:else}
      <AdminButton size="sm" onclick={load}>{at("retry", {}, "Retry")}</AdminButton>
    {/if}
  {:else if rows.length}
    <div class="broadcast-audience-preferences-actions">
      <AdminButton
        size="sm"
        disabled={busy || targets.every((target) => excluded.includes(target))}
        onclick={() => change("exclude_all")}
        >{at("user_broadcast_audiences_exclude_all", {}, "Clear all")}</AdminButton
      >
      <AdminButton size="sm" disabled={busy || !excluded.length} onclick={() => change("reset")}
        >{at("user_broadcast_audiences_reset", {}, "Restore defaults")}</AdminButton
      >
    </div>
    {#each rows as target (target)}
      <label>
        <Checkbox
          checked={!excluded.includes(target)}
          ariaLabel={audienceLabel(target)}
          disabled={busy}
          onCheckedChange={(checked) => change(checked ? "include" : "exclude", target)}
        />
        <span>{audienceLabel(target)}</span>
      </label>
    {/each}
  {:else}
    <small
      >{at("user_broadcast_audiences_empty", {}, "This user matches no broadcast groups.")}</small
    >
  {/if}
</div>

<style>
  .broadcast-audience-preferences {
    display: grid;
    gap: 0.75rem;
    border-top: 1px solid var(--admin-border);
    margin-top: 1rem;
    padding-top: 1rem;
  }
  .broadcast-audience-preferences h4 {
    margin: 0;
  }
  .broadcast-audience-preferences label {
    display: flex;
    align-items: center;
    gap: 0.625rem;
    overflow-wrap: anywhere;
  }
  .broadcast-audience-preferences-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
</style>
