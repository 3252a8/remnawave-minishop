<script lang="ts">
  import { onMount } from "svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminListToolbar,
  } from "$components/patterns/admin/index.js";
  import { Input, Switch } from "$components/ui/index.js";
  import {
    History,
    Plus,
    RefreshCw,
    Search,
    Server,
    Sparkles,
    Trash2,
    TriangleAlert,
  } from "$components/ui/icons.js";
  import { builtApiPath } from "$lib/webapp/publicApi";
  import type { AdminApi } from "../adminStores";
  import PluginImportDialog from "./PluginImportDialog.svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Installation = {
    digest: string;
    version: string;
    publisher: string;
    enabled: boolean;
    status: string;
    source?: { kind: string } | null;
  };
  type Operation = { id: string; action: string; plugin: string; status?: string };
  type Inventory = {
    generation: number;
    installations: Record<string, Installation>;
    bundled: Array<{ id: string; source: string; status: string }>;
    operations: Operation[];
    failed_generation?: number | null;
    failure?: string;
    observations?: Record<string, { generation: number; status: string }>;
  };

  let { api, at }: { api: AdminApi; at: TranslateFn } = $props();
  let inventory = $state<Inventory>({
    generation: 0,
    installations: {},
    bundled: [],
    operations: [],
  });
  let busy = $state(false);
  let error = $state("");
  let query = $state("");
  let importOpen = $state(false);
  const installed = $derived(
    Object.entries(inventory.installations).filter(([id]) =>
      `${id} ${inventory.installations[id].publisher}`.toLowerCase().includes(query.toLowerCase())
    )
  );
  const bundled = $derived(
    inventory.bundled.filter((plugin) => plugin.id.toLowerCase().includes(query.toLowerCase()))
  );
  const failed = $derived(inventory.failed_generation === inventory.generation);

  function responseError(value: unknown, fallback: string): string {
    if (value && typeof value === "object" && "error" in value && typeof value.error === "string")
      return value.error;
    return fallback;
  }

  function statusLabel(plugin: Installation): string {
    if (failed) return at("plugins_runtime_failed", {}, "Could not start; see diagnostics");
    if (plugin.status === "pending_restart")
      return at("plugins_pending_restart", {}, "Applying changes…");
    return plugin.enabled
      ? at("plugins_enabled", {}, "Enabled")
      : at("plugins_disabled", {}, "Disabled");
  }

  function actionLabel(action: string): string {
    const labels: Record<string, string> = {
      install: at("plugins_activity_install", {}, "Installed"),
      enable: at("plugins_activity_enable", {}, "Enabled"),
      disable: at("plugins_activity_disable", {}, "Disabled"),
      remove: at("plugins_activity_remove", {}, "Removed"),
    };
    return labels[action] || action.replaceAll("_", " ");
  }

  async function run(action: () => Promise<void>): Promise<void> {
    if (busy) return;
    busy = true;
    error = "";
    try {
      await action();
    } catch (cause) {
      error = cause instanceof Error ? cause.message.replaceAll("_", " ") : String(cause);
    } finally {
      busy = false;
    }
  }

  async function load(): Promise<void> {
    const result = await api("/admin/plugins");
    if (!result?.ok) throw new Error(responseError(result, "plugins_unavailable"));
    inventory = result as unknown as Inventory;
  }

  async function toggle(id: string, enabled: boolean): Promise<void> {
    await run(async () => {
      const path = builtApiPath<"/api/admin/plugins/{plugin_id}/enabled">(
        `/admin/plugins/${encodeURIComponent(id)}/enabled`
      );
      const result = await api(path, {
        method: "POST",
        body: JSON.stringify({ enabled, generation: inventory.generation }),
      });
      if (!result?.ok) throw new Error(responseError(result, "plugin_update_failed"));
      await load();
    });
  }

  async function remove(id: string): Promise<void> {
    await run(async () => {
      const path = builtApiPath<"/api/admin/plugins/{plugin_id}/remove">(
        `/admin/plugins/${encodeURIComponent(id)}/remove`
      );
      const result = await api(path, {
        method: "POST",
        body: JSON.stringify({ generation: inventory.generation }),
      });
      if (!result?.ok) throw new Error(responseError(result, "plugin_remove_failed"));
      await load();
    });
  }

  onMount(() => {
    void run(load);
  });
</script>

<div class="plugins-section">
  <AdminListToolbar
    total={Object.keys(inventory.installations).length + inventory.bundled.length}
    totalLabel={at("plugins_installed", {}, "Installed")}
  >
    {#snippet search()}
      <div class="plugin-search">
        <Search size={16} />
        <Input
          bind:value={query}
          placeholder={at("plugins_search", {}, "Search plugins")}
          aria-label={at("plugins_search", {}, "Search plugins")}
        />
      </div>
    {/snippet}
    {#snippet actions()}
      <AdminButton size="sm" variant="primary" onclick={() => (importOpen = true)}
        ><Plus size={15} />{at("plugins_add", {}, "Add plugin")}</AdminButton
      >
      <AdminButton size="sm" onclick={() => void run(load)} disabled={busy}
        ><RefreshCw size={14} />{at("btn_refresh", {}, "Refresh")}</AdminButton
      >
    {/snippet}
  </AdminListToolbar>

  {#if error}<p class="admin-error" role="alert">{error}</p>{/if}
  {#if failed}
    <div class="runtime-alert" role="alert">
      <TriangleAlert size={19} />
      <div>
        <strong>{at("plugins_runtime_failed_title", {}, "Plugin startup failed")}</strong>
        <p>
          {at(
            "plugins_runtime_failed_help",
            {},
            "The application is running in recovery mode. Check the migration and startup logs before retrying."
          )}
        </p>
        {#if inventory.failure}<code>{inventory.failure}</code>{/if}
      </div>
    </div>
  {/if}

  <div class="plugin-library-grid">
    {#each bundled as plugin (plugin.id)}
      <article class="plugin-card">
        <div class="plugin-card-head">
          <span class="plugin-icon"><Server size={22} /></span>
          <AdminBadge variant="muted"
            >{at("plugins_managed_by_image", {}, "Managed by image")}</AdminBadge
          >
        </div>
        <div class="plugin-card-body">
          <h3>{plugin.id}</h3>
          <p>{at("plugins_bundled_description", {}, "Included with the application image")}</p>
          <span class="plugin-state"
            ><span class="state-dot"></span>{at("plugins_enabled", {}, "Enabled")}</span
          >
        </div>
      </article>
    {/each}
    {#each installed as [id, plugin] (id)}
      <article class="plugin-card" class:active={plugin.enabled} data-plugin-id={id}>
        <div class="plugin-card-head">
          <span class="plugin-icon"><Sparkles size={22} /></span>
          <AdminBadge>{plugin.version}</AdminBadge>
        </div>
        <div class="plugin-card-body">
          <h3>{id}</h3>
          <p>{at("plugins_publisher", {}, "Publisher")}: {plugin.publisher}</p>
          <div class="plugin-card-controls">
            <span
              class="plugin-state"
              class:pending={plugin.status === "pending_restart" || failed}
            >
              <span class="state-dot"></span>{statusLabel(plugin)}
            </span>
            <Switch.Root
              aria-label={at("plugins_toggle_named", { name: id }, "Enable {name}")}
              checked={plugin.enabled}
              onCheckedChange={(checked) => void toggle(id, checked)}
              disabled={busy}
              class="admin-switch-root"><Switch.Thumb class="admin-switch-thumb" /></Switch.Root
            >
          </div>
          <details class="plugin-details">
            <summary>{at("plugins_details", {}, "Package details")}</summary>
            <dl>
              <div>
                <dt>SHA-256</dt>
                <dd class="digest">{plugin.digest}</dd>
              </div>
              <div>
                <dt>{at("plugins_source", {}, "Source")}</dt>
                <dd>
                  {plugin.source?.kind === "image"
                    ? at("plugins_managed_by_image", {}, "Managed by image")
                    : plugin.source?.kind || at("plugins_uploaded", {}, "Uploaded ZIP")}
                </dd>
              </div>
            </dl>
            {#if !plugin.enabled && plugin.source?.kind !== "image"}
              <AdminButton size="sm" disabled={busy} onclick={() => void remove(id)}
                ><Trash2 size={14} />{at("plugins_remove", {}, "Remove package")}</AdminButton
              >
            {/if}
          </details>
        </div>
      </article>
    {/each}
    {#if !query.trim()}
      <button type="button" class="plugin-add-card" onclick={() => (importOpen = true)}>
        <span class="add-symbol"><Plus size={25} /></span>
        <strong>{at("plugins_add", {}, "Add plugin")}</strong>
        <span
          >{at(
            "plugins_add_hint",
            {},
            "Upload a signed ZIP or choose a public Git repository."
          )}</span
        >
      </button>
    {/if}
  </div>

  {#if !installed.length && !bundled.length && query.trim()}
    <AdminEmptyState
      >{at("plugins_no_results", {}, "No plugins match your search.")}</AdminEmptyState
    >
  {/if}

  {#if inventory.operations.length}
    <details class="plugin-activity">
      <summary
        ><History size={16} />{at("plugins_activity", {}, "Recent changes")}
        <span>{inventory.operations.length}</span></summary
      >
      <ul>
        {#each inventory.operations.slice(-8).reverse() as operation (operation.id)}
          <li>
            <strong>{actionLabel(operation.action)}</strong><span>{operation.plugin}</span
            >{#if operation.status}<AdminBadge
                variant={operation.status === "completed" ? "success" : "muted"}
                >{operation.status}</AdminBadge
              >{/if}
          </li>
        {/each}
      </ul>
    </details>
  {/if}
</div>

<PluginImportDialog
  {api}
  {at}
  open={importOpen}
  generation={inventory.generation}
  onclose={() => (importOpen = false)}
  oninstalled={() => run(load)}
/>

<style>
  .plugins-section {
    display: grid;
    gap: 16px;
  }
  .plugin-search {
    position: relative;
    display: flex;
    align-items: center;
  }
  .plugin-search :global(svg) {
    position: absolute;
    left: 10px;
    color: var(--admin-muted);
    pointer-events: none;
  }
  .plugin-search :global(input) {
    padding-left: 34px;
  }
  .plugin-library-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 16px;
  }
  .plugin-card {
    display: flex;
    flex-direction: column;
    min-width: 0;
    border: 1px solid var(--admin-border);
    border-radius: 12px;
    background: var(--admin-surface);
    overflow: hidden;
  }
  .plugin-card.active {
    border-color: color-mix(in srgb, var(--accent) 65%, var(--admin-border));
  }
  .plugin-card-head {
    display: flex;
    justify-content: space-between;
    align-items: start;
    gap: 12px;
    padding: 16px;
    border-bottom: 1px solid var(--admin-border);
    background: var(--admin-surface-2);
  }
  .plugin-icon,
  .add-symbol {
    display: grid;
    place-items: center;
    width: 46px;
    height: 46px;
    border: 1px solid var(--admin-border);
    border-radius: 12px;
    color: var(--accent);
    background: var(--admin-surface);
  }
  .plugin-card-body {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 10px;
    min-width: 0;
    padding: 16px;
  }
  h3,
  p {
    margin: 0;
  }
  h3 {
    font-size: 15px;
  }
  .plugin-card-body > p {
    min-height: 38px;
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.6;
    overflow-wrap: anywhere;
  }
  .plugin-card-controls {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    margin-top: auto;
  }
  .plugin-state {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    color: var(--admin-muted);
    font-size: 11px;
  }
  .state-dot {
    flex: none;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--accent);
  }
  .plugin-state.pending .state-dot {
    background: var(--warning, #d7a33b);
  }
  .plugin-details {
    padding-top: 10px;
    border-top: 1px solid var(--admin-border);
    font-size: 11px;
  }
  .plugin-details summary {
    cursor: pointer;
    color: var(--admin-muted);
  }
  .plugin-details dl {
    display: grid;
    gap: 8px;
    margin: 10px 0;
  }
  .plugin-details dl > div {
    display: grid;
    gap: 3px;
  }
  .plugin-details dt {
    color: var(--admin-muted);
  }
  .plugin-details dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .digest {
    font-family: ui-monospace, monospace;
  }
  .plugin-add-card {
    display: grid;
    justify-items: center;
    align-content: center;
    gap: 12px;
    min-height: 210px;
    padding: 25px;
    border: 1px dashed var(--admin-border-strong);
    border-radius: 12px;
    color: var(--admin-text);
    background: color-mix(in srgb, var(--admin-surface) 55%, transparent);
    font: inherit;
    text-align: center;
    cursor: pointer;
  }
  .plugin-add-card:hover {
    border-color: var(--accent);
  }
  .plugin-add-card span:last-child {
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.6;
  }
  .runtime-alert {
    display: flex;
    align-items: start;
    gap: 12px;
    padding: 14px;
    border: 1px solid color-mix(in srgb, var(--danger) 55%, var(--admin-border));
    border-radius: 10px;
    background: color-mix(in srgb, var(--danger) 8%, var(--admin-surface));
  }
  .runtime-alert > :global(svg) {
    flex: none;
    color: var(--danger);
  }
  .runtime-alert p {
    margin-top: 4px;
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.6;
  }
  .runtime-alert code {
    display: block;
    margin-top: 7px;
    font-size: 11px;
    overflow-wrap: anywhere;
  }
  .plugin-activity {
    padding: 14px;
    border: 1px solid var(--admin-border);
    border-radius: 12px;
    background: var(--admin-surface);
  }
  .plugin-activity summary {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 650;
  }
  .plugin-activity summary span {
    color: var(--admin-muted);
    font-weight: 400;
  }
  .plugin-activity ul {
    list-style: none;
    margin: 12px 0 0;
    padding: 0;
  }
  .plugin-activity li {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 0;
    border-top: 1px solid var(--admin-border);
    font-size: 12px;
  }
  .plugin-activity li span {
    color: var(--admin-muted);
  }
  @media (max-width: 1050px) {
    .plugin-library-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
  @media (max-width: 650px) {
    .plugin-library-grid {
      grid-template-columns: 1fr;
    }
    .plugin-add-card {
      min-height: 160px;
    }
  }
</style>
