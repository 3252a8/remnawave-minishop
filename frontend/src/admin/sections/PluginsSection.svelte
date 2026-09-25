<script lang="ts">
  import { onMount } from "svelte";
  import {
    AdminButton,
    AdminEmptyState,
    AdminListToolbar,
  } from "$components/patterns/admin/index.js";
  import { Dialog, Input, Switch, Tabs } from "$components/ui/index.js";
  import {
    ArrowLeft,
    Plus,
    RefreshCw,
    Search,
    Settings,
    Sparkles,
    Trash2,
    TriangleAlert,
  } from "$components/ui/icons.js";
  import { builtApiPath } from "$lib/webapp/publicApi";
  import type { AdminApi } from "../adminStores";
  import PluginApplyDialog from "./PluginApplyDialog.svelte";
  import PluginImportDialog from "./PluginImportDialog.svelte";
  import PluginRemoveDialog from "./PluginRemoveDialog.svelte";
  import PluginHost from "./PluginHost.svelte";
  import { responseError } from "./pluginPackageErrors";
  import PluginOperations from "./PluginOperations.svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Installation = {
    digest: string;
    version: string;
    publisher: string;
    enabled: boolean;
    status: string;
    name?: string;
    description?: string;
    preview_url?: string;
    source?: { kind: string; url?: string; ref?: string; sha256?: string } | null;
  };
  type PluginCard = { id: string; installation?: Installation; bundled: boolean };
  type SettingsView = {
    id: string;
    view: string;
    label?: string;
    i18nKey?: string;
    order?: number;
  };
  type RuntimePlugin = {
    id: string;
    digest: string;
    entry: string;
    settings_tabs?: SettingsView[];
  };
  type Inventory = {
    generation: number;
    installations: Record<string, Installation>;
    bundled: Array<{ id: string; source: string; status: string }>;
    failed_generation?: number | null;
    failure?: string;
    observations?: Record<string, { generation: number; status: string }>;
    operations?: Array<{
      id: string;
      action: string;
      plugin: string;
      digest?: string;
      status?: string;
    }>;
  };
  let { api, at }: { api: AdminApi; at: TranslateFn } = $props();
  let inventory = $state<Inventory>({
    generation: 0,
    installations: {},
    bundled: [],
  });
  let busy = $state(false);
  let error = $state("");
  let query = $state("");
  let importOpen = $state(false);
  let selectedId = $state("");
  let activeTab = $state("overview");
  let packageOpen = $state(false);
  let packageId = $state("");
  let runtime = $state<RuntimePlugin | null>(null);
  let runtimeLoading = $state(false);
  let activeSettingsView = $state("");
  let availableUpdates = $state<Record<string, boolean>>({});
  let removeDialogId = $state("");
  let removeName = $state("");
  let removeStage = $state<"confirm" | "removing" | "restarting" | "complete" | "failed">(
    "confirm"
  );
  let removeError = $state("");
  let removeConfirmed = $state(false);
  let applyBusy = $state(false);
  let applyDialog = $state<ReturnType<typeof PluginApplyDialog> | null>(null);
  const cards = $derived.by(() => {
    const byId = new Map<string, PluginCard>();
    for (const plugin of inventory.bundled) byId.set(plugin.id, { id: plugin.id, bundled: true });
    for (const [id, installation] of Object.entries(inventory.installations)) {
      byId.set(id, { id, bundled: byId.has(id), installation });
    }
    return [...byId.values()].filter(({ id, installation }) =>
      `${id} ${installation?.name || ""} ${installation?.publisher || ""}`
        .toLowerCase()
        .includes(query.trim().toLowerCase())
    );
  });
  const selected = $derived(cards.find((card) => card.id === selectedId));
  const packageCard = $derived(cards.find((card) => card.id === packageId));
  const settingsTabs = $derived(
    [...(runtime?.settings_tabs || [])].sort((a, b) => (a.order || 0) - (b.order || 0))
  );
  const failed = $derived(inventory.failed_generation === inventory.generation);

  function statusLabel(plugin: Installation): string {
    if (failed) return at("plugins_runtime_failed", {}, "Could not start; see diagnostics");
    if (plugin.status === "pending_restart")
      return at("plugins_pending_restart", {}, "Applying changes…");
    return plugin.enabled
      ? at("plugins_enabled", {}, "Enabled")
      : at("plugins_disabled", {}, "Disabled");
  }

  function routeToPlugin(id: string, tab = "overview"): void {
    selectedId = id;
    activeTab = tab;
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      if (id) url.searchParams.set("plugin", id);
      else url.searchParams.delete("plugin");
      if (id && tab !== "overview") url.searchParams.set("tab", tab);
      else url.searchParams.delete("tab");
      window.history.pushState(null, "", url);
    }
    if (!id) runtime = null;
    else if (runtime?.id !== id) void loadRuntime(id);
  }

  async function loadRuntime(id: string): Promise<void> {
    runtime = null;
    runtimeLoading = true;
    try {
      const result = await api("/admin/plugins/runtime");
      if (selectedId === id && result?.ok) {
        runtime = (result.plugins as RuntimePlugin[]).find((plugin) => plugin.id === id) || null;
        activeSettingsView =
          [...(runtime?.settings_tabs || [])].sort((a, b) => (a.order || 0) - (b.order || 0))[0]
            ?.id || "";
      }
    } catch {
      // The package overview remains usable when an optional frontend is unavailable.
    } finally {
      if (selectedId === id) runtimeLoading = false;
    }
  }

  async function run(action: () => Promise<void>): Promise<void> {
    if (busy || applyBusy) return;
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

  async function refreshInventory(): Promise<Inventory> {
    const result = await api("/admin/plugins");
    if (!result?.ok) throw new Error(responseError(result, "plugins_unavailable"));
    inventory = result as unknown as Inventory;
    return inventory;
  }

  async function load(): Promise<void> {
    await refreshInventory();
    void loadUpdates();
  }

  async function loadUpdates(): Promise<void> {
    try {
      const result = await api("/admin/plugins/updates");
      if (result?.ok) availableUpdates = (result.updates || {}) as Record<string, boolean>;
    } catch {
      // Update discovery is optional and never blocks inventory or settings.
    }
  }

  function toggle(id: string, enabled: boolean): void {
    void applyDialog?.toggle(
      id,
      inventory.installations[id]?.name || id,
      enabled,
      inventory.generation
    );
  }

  function install(operation: {
    id: string;
    name: string;
    digest: string;
    operationId: string;
    generation: number;
  }): void {
    applyDialog?.install(operation, Boolean(inventory.installations[operation.id]));
  }

  function openRemove(id: string, name: string): void {
    removeDialogId = id;
    removeName = name;
    removeStage = "confirm";
    removeError = "";
    removeConfirmed = false;
  }

  function closeRemove(): void {
    if (removeStage === "removing" || removeStage === "restarting") return;
    removeDialogId = "";
  }

  function removeErrorLabel(code: string): string {
    if (code === "generation_conflict")
      return at("plugins_generation_conflict", {}, "The installation changed. Refresh and retry.");
    if (code === "image_plugin_cannot_remove")
      return at("plugins_image_remove_error", {}, "Image plugins are removed with the image.");
    return at("plugins_remove_failed", {}, "The package could not be removed. Try again.");
  }

  async function remove(id: string): Promise<void> {
    if (busy || applyBusy) return;
    busy = true;
    removeStage = "removing";
    removeError = "";
    const path = builtApiPath<"/api/admin/plugins/{plugin_id}/remove">(
      `/admin/plugins/${encodeURIComponent(id)}/remove`
    );
    let acknowledged = false;
    try {
      try {
        const result = await api(path, {
          method: "POST",
          body: JSON.stringify({ generation: inventory.generation }),
        });
        if (!result?.ok) {
          removeError = removeErrorLabel(responseError(result, "plugin_remove_failed"));
          removeStage = "failed";
          return;
        }
        acknowledged = true;
      } catch {
        // The supervisor may stop the web process after persisting the removal.
        // Confirm the resulting generation before treating a lost response as failure.
      }

      for (let attempt = 0; attempt < 90; attempt += 1) {
        try {
          const current = await refreshInventory();
          if (!(id in current.installations)) {
            removeConfirmed = true;
            removeStage = "restarting";
            if (selectedId === id) routeToPlugin("");
            const ready = ["backend", "worker"].every(
              (role) =>
                current.observations?.[role]?.generation === current.generation &&
                current.observations?.[role]?.status === "active"
            );
            if (ready) {
              removeStage = "complete";
              void loadUpdates();
              return;
            }
            if (current.failed_generation === current.generation) {
              removeError = at(
                "plugins_remove_restart_failed",
                {},
                "The package was removed, but the application did not restart normally. Check diagnostics."
              );
              removeStage = "failed";
              return;
            }
          } else if (!acknowledged && attempt >= 5) {
            removeError = at(
              "plugins_remove_not_confirmed",
              {},
              "Removal was not confirmed. Refresh the plugin list before retrying."
            );
            removeStage = "failed";
            return;
          }
        } catch {
          // Backend and worker may be unavailable briefly during the generation switch.
        }
        await new Promise((resolve) => setTimeout(resolve, attempt < 5 ? 1000 : 4000));
      }
      removeError = at(
        "plugins_remove_waiting",
        {},
        "The restart is taking longer than expected. Refresh the list to check its status."
      );
      removeStage = "failed";
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    void run(load);
    const sync = () => {
      const url = new URL(window.location.href);
      selectedId = url.searchParams.get("plugin") || "";
      activeTab = url.searchParams.get("tab") || "overview";
      if (selectedId && runtime?.id !== selectedId) void loadRuntime(selectedId);
    };
    sync();
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  });
</script>

<div class="plugins-section">
  {#if !selectedId}
    <AdminListToolbar
      total={new Set([
        ...Object.keys(inventory.installations),
        ...inventory.bundled.map((item) => item.id),
      ]).size}
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
        <AdminButton
          size="sm"
          variant="primary"
          disabled={busy || applyBusy}
          onclick={() => (importOpen = true)}
          ><Plus size={15} />{at("plugins_add", {}, "Add plugin")}</AdminButton
        >
        <AdminButton size="sm" onclick={() => void run(load)} disabled={busy || applyBusy}
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
      {#each cards as card (card.id)}
        <article
          class="plugin-card"
          class:active={card.installation?.enabled || card.bundled}
          data-plugin-id={card.id}
        >
          <div class="plugin-preview">
            <div class="plugin-preview-fallback"><Sparkles size={36} /></div>
            {#if card.installation?.preview_url}
              <img
                src={card.installation.preview_url}
                alt={at(
                  "plugins_preview_named",
                  { name: card.installation.name || card.id },
                  "Preview of {name}"
                )}
                loading="lazy"
                onload={(event) => {
                  (event.currentTarget as HTMLImageElement).style.display = "";
                }}
                onerror={(event) => {
                  (event.currentTarget as HTMLImageElement).style.display = "none";
                }}
              />
            {/if}
          </div>
          <div class="plugin-card-body">
            <div class="plugin-card-title">
              <h3>{card.installation?.name || card.id}</h3>
              {#if availableUpdates[card.id]}<span
                  class="plugin-update-dot"
                  title={at("plugins_update_available", {}, "Update available")}
                  aria-label={at("plugins_update_available", {}, "Update available")}
                ></span>{/if}
              {#if card.installation}
                <button
                  type="button"
                  class="plugin-version"
                  onclick={() => {
                    packageId = card.id;
                    packageOpen = true;
                  }}
                  aria-label={at(
                    "plugins_version_details",
                    { version: card.installation?.version },
                    "Package version {version}: details"
                  )}>{card.installation.version}</button
                >
              {/if}
            </div>
            <p>
              {card.installation?.description ||
                at("plugins_bundled_description", {}, "Included with the application image")}
            </p>
            <div class="plugin-card-controls">
              <span
                class="plugin-state"
                class:pending={card.installation?.status === "pending_restart" || failed}
                ><span class="state-dot"></span>{card.installation
                  ? statusLabel(card.installation)
                  : at("plugins_enabled", {}, "Enabled")}</span
              >
              {#if card.installation}
                <Switch.Root
                  aria-label={at("plugins_toggle_named", { name: card.id }, "Enable {name}")}
                  checked={card.installation.enabled}
                  onCheckedChange={(checked) => void toggle(card.id, checked)}
                  disabled={busy || applyBusy}
                  class="admin-switch-root"><Switch.Thumb class="admin-switch-thumb" /></Switch.Root
                >
              {/if}
            </div>
            <div class="plugin-card-actions">
              <AdminButton size="sm" onclick={() => routeToPlugin(card.id, "settings")}
                ><Settings size={14} />{at("plugins_settings", {}, "Settings")}</AdminButton
              >
            </div>
          </div>
        </article>
      {/each}
      {#if !query.trim()}
        <button
          type="button"
          class="plugin-add-card"
          disabled={busy || applyBusy}
          onclick={() => (importOpen = true)}
        >
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

    {#if !cards.length && query.trim()}
      <AdminEmptyState
        >{at("plugins_no_results", {}, "No plugins match your search.")}</AdminEmptyState
      >
    {/if}
  {:else if selected}
    <div class="plugin-detail">
      <AdminButton size="sm" variant="ghost" onclick={() => routeToPlugin("")}
        ><ArrowLeft size={15} />{at("plugins_back", {}, "All plugins")}</AdminButton
      >
      <div class="plugin-detail-heading">
        <h3>{selected.installation?.name || selected.id}</h3>
        {#if availableUpdates[selected.id]}<span
            class="plugin-update-dot"
            title={at("plugins_update_available", {}, "Update available")}
          ></span>{/if}
        {#if selected.installation}<button
            type="button"
            class="plugin-version"
            onclick={() => {
              packageId = selected.id;
              packageOpen = true;
            }}>{selected.installation.version}</button
          >{/if}
      </div>
      <Tabs.Root
        class="admin-tabs-root"
        value={activeTab}
        onValueChange={(value) => routeToPlugin(selected.id, value)}
      >
        <Tabs.List
          class="admin-tabs-list"
          aria-label={at("plugins_detail_tabs", {}, "Plugin details")}
        >
          <Tabs.Trigger value="overview" class="admin-tabs-trigger"
            >{at("plugins_overview", {}, "Overview")}</Tabs.Trigger
          >
          <Tabs.Trigger value="settings" class="admin-tabs-trigger"
            >{at("plugins_settings", {}, "Settings")}</Tabs.Trigger
          >
          <Tabs.Trigger value="updates" class="admin-tabs-trigger"
            >{at("plugins_updates", {}, "Updates")}</Tabs.Trigger
          >
          <Tabs.Trigger value="operations" class="admin-tabs-trigger"
            >{at("plugins_operations")}</Tabs.Trigger
          >
        </Tabs.List>
      </Tabs.Root>
      {#if activeTab === "overview"}
        <div class="plugin-detail-content">
          <p>
            {selected.installation?.description ||
              at("plugins_bundled_description", {}, "Included with the application image")}
          </p>
          <p>
            {at("plugins_publisher", {}, "Publisher")}: {selected.installation?.publisher || "—"}
          </p>
        </div>
      {:else if activeTab === "operations"}
        <PluginOperations {api} {at} owner={selectedId} />
      {:else if activeTab === "settings"}
        <div
          class="plugin-detail-content"
          class:plugin-settings-content={runtime && settingsTabs.length > 0}
        >
          {#if runtimeLoading}
            <p role="status">{at("loading", {}, "Loading…")}</p>
          {:else if runtime && settingsTabs.length}
            {#if settingsTabs.length > 1}
              <Tabs.Root
                class="admin-tabs-root"
                value={activeSettingsView}
                onValueChange={(value) => (activeSettingsView = value)}
              >
                <Tabs.List
                  class="admin-tabs-list"
                  aria-label={at("plugins_settings", {}, "Settings")}
                >
                  {#each settingsTabs as view (view.id)}
                    <Tabs.Trigger value={view.id} class="admin-tabs-trigger"
                      >{at(view.i18nKey || view.id, {}, view.label || view.id)}</Tabs.Trigger
                    >
                  {/each}
                </Tabs.List>
              </Tabs.Root>
            {/if}
            {#each settingsTabs.filter((view) => view.id === activeSettingsView) as view (view.id)}
              <section aria-label={at(view.i18nKey || view.id, {}, view.label || view.id)}>
                <PluginHost runtimeViewId={view.view} runtimeEntry={runtime.entry} {at} />
              </section>
            {/each}
          {:else}
            <p>{at("plugins_no_settings", {}, "This plugin does not provide settings yet.")}</p>
          {/if}
        </div>
      {:else if activeTab === "updates"}
        <div class="plugin-detail-content">
          {#if availableUpdates[selected.id]}<p class="plugin-update-message">
              {at("plugins_update_available", {}, "Update available")}
            </p>{/if}
          {#if selected.installation?.source?.kind === "image" || selected.bundled}
            <p>
              {at(
                "plugins_image_update_help",
                {},
                "This plugin is updated with the application image. Install a new image to update it."
              )}
            </p>
          {:else if selected.installation?.source?.url}
            <p>
              {at(
                "plugins_repository_update_help",
                {},
                "Updates are installed from a verified package in the plugin repository."
              )}
            </p>
          {:else}
            <p>
              {at(
                "plugins_archive_update_help",
                {},
                "Upload a newer signed package from the same publisher to update this plugin."
              )}
            </p>
          {/if}
          {#if selected.installation && selected.installation.source?.kind !== "image"}
            <div class="plugin-update-actions">
              <AdminButton
                size="sm"
                onclick={() => (importOpen = true)}
                disabled={busy || applyBusy}
                >{selected.installation.source?.url
                  ? at("plugins_check_update", {}, "Check and install update")
                  : at("plugins_add", {}, "Add plugin")}</AdminButton
              >
              <AdminButton
                size="sm"
                variant="danger"
                disabled={busy || applyBusy}
                onclick={() => openRemove(selected.id, selected.installation?.name || selected.id)}
                ><Trash2 size={14} />{at("plugins_remove", {}, "Remove package")}</AdminButton
              >
            </div>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
</div>

<PluginImportDialog
  {api}
  {at}
  open={importOpen}
  generation={inventory.generation}
  initialRepository={selected?.installation?.source?.url || ""}
  initialRef={selected?.installation?.source?.ref || ""}
  onclose={() => (importOpen = false)}
  oninstall={install}
/>

<PluginApplyDialog
  bind:this={applyDialog}
  {api}
  {at}
  blocked={busy}
  oninventory={refreshInventory}
  onready={(id) => {
    void loadUpdates();
    if (selectedId === id) void loadRuntime(id);
  }}
  onbusy={(value) => (applyBusy = value)}
/>

<Dialog
  open={packageOpen}
  title={at("plugins_details", {}, "Package details")}
  closeLabel={at("close", {}, "Close")}
  onclose={() => (packageOpen = false)}
  class="admin-dialog plugin-package-dialog"
>
  {#if packageCard?.installation}
    <dl class="plugin-package-meta">
      <div>
        <dt>{at("plugins_name", {}, "Name")}</dt>
        <dd>{packageCard.installation.name || packageCard.id}</dd>
      </div>
      <div>
        <dt>{at("plugins_version", {}, "Version")}</dt>
        <dd>{packageCard.installation.version}</dd>
      </div>
      <div>
        <dt>{at("plugins_publisher", {}, "Publisher")}</dt>
        <dd>{packageCard.installation.publisher}</dd>
      </div>
      <div>
        <dt>{at("plugins_source", {}, "Source")}</dt>
        <dd>
          {packageCard.installation.source?.kind === "image"
            ? at("plugins_image_source", {}, "Application image")
            : packageCard.installation.source?.kind || at("plugins_uploaded", {}, "Uploaded ZIP")}
        </dd>
      </div>
      <div>
        <dt>SHA-256</dt>
        <dd class="digest">{packageCard.installation.digest}</dd>
      </div>
    </dl>
  {/if}
</Dialog>

<PluginRemoveDialog
  {at}
  open={Boolean(removeDialogId)}
  name={removeName}
  stage={removeStage}
  error={removeError}
  confirmed={removeConfirmed}
  onclose={closeRemove}
  onremove={() => void remove(removeDialogId)}
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
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
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
  .plugin-preview {
    position: relative;
    aspect-ratio: 16 / 10;
    overflow: hidden;
    border-bottom: 1px solid var(--admin-border);
    background: var(--admin-surface-2);
  }
  .plugin-preview img {
    position: absolute;
    inset: 0;
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .plugin-preview-fallback {
    display: grid;
    place-items: center;
    width: 100%;
    height: 100%;
    color: var(--accent);
    background:
      radial-gradient(
        circle at 50% 50%,
        color-mix(in srgb, var(--accent) 18%, transparent),
        transparent 65%
      ),
      var(--admin-surface-2);
  }
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
  .plugin-card-title,
  .plugin-detail-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .plugin-version {
    flex: none;
    padding: 3px 8px;
    border: 1px solid var(--admin-border);
    border-radius: 999px;
    color: var(--admin-muted);
    background: var(--admin-surface-2);
    font: inherit;
    font-size: 11px;
    cursor: pointer;
  }
  .plugin-version:hover {
    border-color: var(--accent);
    color: var(--admin-text);
  }
  .plugin-update-dot {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--danger, #ec4d62);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--danger, #ec4d62) 18%, transparent);
  }
  .plugin-update-message {
    color: var(--danger, #ec4d62) !important;
    font-weight: 650;
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
  .plugin-card-actions {
    padding-top: 12px;
    border-top: 1px solid var(--admin-border);
  }
  .plugin-detail {
    display: grid;
    gap: 16px;
  }
  .plugin-detail > :global(button:first-child) {
    justify-self: start;
  }
  .plugin-detail-content {
    padding: 18px;
    border: 1px solid var(--admin-border);
    border-radius: 12px;
    background: var(--admin-surface);
  }
  .plugin-settings-content {
    padding: 0;
    border: 0;
    background: transparent;
  }
  .plugin-detail-content p {
    color: var(--admin-muted);
    font-size: 13px;
    line-height: 1.6;
  }
  .plugin-update-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-top: 8px;
  }
  .plugin-package-meta {
    display: grid;
    gap: 12px;
    margin: 0;
  }
  .plugin-package-meta > div {
    display: grid;
    gap: 4px;
  }
  .plugin-package-meta dt {
    color: var(--admin-muted);
    font-size: 12px;
  }
  .plugin-package-meta dd {
    margin: 0;
    overflow-wrap: anywhere;
    font-size: 13px;
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
