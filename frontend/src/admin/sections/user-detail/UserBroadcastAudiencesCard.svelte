<script lang="ts">
  import { onMount } from "svelte";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import NotificationPreferenceSwitch from "$components/patterns/NotificationPreferenceSwitch.svelte";
  import { getAdminApi, getBroadcastStore } from "$lib/admin/context";
  import { adminErrorMessage } from "$lib/admin/errors";
  import { buildAdminUserBroadcastAudiencesPath, unwrap } from "$lib/webapp/publicApi";
  import type { TranslateFn } from "./userDetailTypes.js";

  let { at, userId }: { at: TranslateFn; userId: number | string } = $props();

  const api = getAdminApi();
  const broadcastStore = getBroadcastStore();
  const headingId = $props.id();
  const path = $derived(buildAdminUserBroadcastAudiencesPath(userId));
  let targets = $state<string[] | null>(null);
  let excluded = $state<string[]>([]);
  let busy = $state(false);
  let error = $state("");
  type Action = "exclude" | "include" | "exclude_all" | "reset";

  const audienceGroups = $derived.by(() => {
    const remaining = new Set([...(targets || []), ...excluded]);
    const groups = new Map<string, { target: string; label: string }[]>();
    const other = at("user_broadcast_audiences_other", {}, "Other groups");

    function add(group: string, target: string, label: string): void {
      const row = { target, label };
      const rows = groups.get(group);
      if (rows) rows.push(row);
      else groups.set(group, [row]);
    }

    for (const option of broadcastStore.BROADCAST_TARGET_OPTIONS) {
      if (remaining.delete(option.value)) {
        add(option.group || other, option.value, option.label);
      }
    }
    for (const target of remaining) {
      const label =
        target === "without_required_channel"
          ? at(
              "broadcast_target_without_required_channel",
              {},
              "Not subscribed to the required group or channel"
            )
          : target;
      add(other, target, label);
    }
    return [...groups];
  });

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

<section class="audiences-panel" aria-labelledby={headingId}>
  <div class="audiences-intro">
    <h3 id={headingId}>{at("user_broadcast_audiences_title", {}, "Broadcast groups")}</h3>
    <small>
      {at(
        "user_broadcast_audiences_hint",
        {},
        "Turn off a group to exclude this user from it. They can still receive a broadcast through another selected group."
      )}
    </small>
  </div>

  {#if error}
    <small class="admin-field-error" role="alert">{error}</small>
  {/if}
  {#if targets === null}
    {#if busy}
      <small role="status">{at("loading", {}, "Loading")}</small>
    {:else}
      <div><AdminButton size="sm" onclick={load}>{at("retry", {}, "Retry")}</AdminButton></div>
    {/if}
  {:else if audienceGroups.length}
    <div class="audiences-groups">
      {#each audienceGroups as [group, rows] (group)}
        <div class="audiences-group">
          <h4>{group}</h4>
          {#each rows as { target, label } (target)}
            <div class="audience-row">
              <span>{label}</span>
              <NotificationPreferenceSwitch
                checked={!excluded.includes(target)}
                ariaLabel={label}
                disabled={busy}
                onCheckedChange={(checked) => change(checked ? "include" : "exclude", target)}
              />
            </div>
          {/each}
        </div>
      {/each}
    </div>
    <div class="audiences-actions">
      <AdminButton
        size="sm"
        disabled={busy || targets.every((target) => excluded.includes(target))}
        onclick={() => change("exclude_all")}
        >{at("user_broadcast_audiences_exclude_all", {}, "Turn off all")}</AdminButton
      >
      <AdminButton size="sm" disabled={busy || !excluded.length} onclick={() => change("reset")}>
        {at("user_broadcast_audiences_reset", {}, "Restore defaults")}
      </AdminButton>
    </div>
  {:else}
    <small
      >{at("user_broadcast_audiences_empty", {}, "This user matches no broadcast groups.")}</small
    >
  {/if}
</section>

<style>
  .audiences-panel {
    display: grid;
    gap: 12px;
    margin-top: 16px;
    padding: 18px;
    border: 1px solid var(--border);
    border-radius: var(--radius-card, var(--radius));
    background: var(--panel);
    color: var(--text);
  }

  .audiences-intro {
    display: grid;
    gap: 4px;
  }

  .audiences-intro h3 {
    margin: 0;
    font-size: 16px;
  }

  .audiences-panel small:not([role="alert"]) {
    color: var(--muted);
    line-height: 1.45;
  }

  .audiences-groups {
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: var(--radius-inner, var(--radius));
  }

  .audiences-group + .audiences-group,
  .audience-row {
    border-top: 1px solid var(--border);
  }

  .audiences-group h4 {
    margin: 0;
    padding: 6px 14px;
    background: var(--panel-2);
    color: var(--muted);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  .audience-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: 12px;
    min-height: 38px;
    padding: 6px 22px 6px 14px;
    font-size: 13px;
    font-weight: 600;
    overflow-wrap: anywhere;
  }

  .audiences-actions {
    display: flex;
    justify-content: flex-end;
    flex-wrap: wrap;
    gap: 8px;
  }

  @media (max-width: 640px) {
    .audiences-panel {
      padding: 15px;
    }

    .audience-row {
      min-height: 44px;
      padding: 9px 14px;
    }

    .audiences-actions {
      justify-content: flex-start;
    }
  }

  @media (max-width: 420px) {
    .audiences-actions {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
