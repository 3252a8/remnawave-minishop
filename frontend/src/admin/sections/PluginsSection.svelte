<script lang="ts">
  import { onMount } from "svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminListToolbar,
  } from "$components/patterns/admin/index.js";
  import { FileInput, Input } from "$components/ui/index.js";
  import { Plus, RefreshCw, Upload } from "$components/ui/icons.js";
  import { builtApiPath } from "$lib/webapp/publicApi";
  import type { AdminApi } from "../adminStores";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Installation = {
    digest: string;
    version: string;
    publisher: string;
    enabled: boolean;
    status: string;
    source?: { kind: string } | null;
  };
  type Manifest = {
    id: string;
    version: string;
    publisher: string;
    name?: string;
    description?: string;
  };
  type Candidate = {
    operation_id?: string;
    digest: string;
    manifest: Manifest;
    trusted: boolean;
    trust_reason: string;
    source?: { url: string; ref: string; commit: string; artifact: string };
  };
  type Inventory = {
    generation: number;
    installations: Record<string, Installation>;
    bundled: Array<{ id: string; source: string; status: string }>;
    operations: Array<{ id: string; action: string; plugin: string }>;
  };

  let { api, at }: { api: AdminApi; at: TranslateFn } = $props();
  let inventory = $state<Inventory>({
    generation: 0,
    installations: {},
    bundled: [],
    operations: [],
  });
  let candidate = $state<Candidate | null>(null);
  let selectedFile = $state<File | null>(null);
  let fileInput = $state<HTMLInputElement | null>(null);
  let busy = $state(false);
  let error = $state("");
  let publisherKey = $state("");
  let publisherFingerprint = $state("");
  let repositoryUrl = $state("");
  let repositoryRef = $state("");
  let tab = $state<"installed" | "add" | "operations">("installed");

  const installed = $derived(Object.entries(inventory.installations));

  function explain(code: string): string {
    const messages: Record<string, string> = {
      publisher_not_trusted: at(
        "plugins_publisher_not_trusted",
        {},
        "Trust this publisher before installing."
      ),
      plugin_managed_by_image: at(
        "plugins_image_conflict",
        {},
        "This plugin is supplied by the current image."
      ),
      generation_conflict: at(
        "plugins_generation_conflict",
        {},
        "The installation changed. Refresh and try again."
      ),
      invalid_package_signature: at(
        "plugins_invalid_signature",
        {},
        "Package signature is invalid."
      ),
    };
    return messages[code] || code.replaceAll("_", " ");
  }

  function responseError(value: unknown, fallback: string): string {
    if (value && typeof value === "object" && "error" in value && typeof value.error === "string")
      return value.error;
    return fallback;
  }

  async function run(action: () => Promise<void>): Promise<void> {
    if (busy) return;
    busy = true;
    error = "";
    try {
      await action();
    } catch (cause) {
      error = explain(cause instanceof Error ? cause.message : String(cause));
    } finally {
      busy = false;
    }
  }

  async function load(): Promise<void> {
    const result = await api("/admin/plugins");
    if (!result?.ok) throw new Error(responseError(result, "plugins_unavailable"));
    inventory = result as unknown as Inventory;
  }

  async function inspect(file: File): Promise<void> {
    selectedFile = file;
    candidate = null;
    await run(async () => {
      const form = new FormData();
      form.append("file", file);
      const result = await api("/admin/plugins/preview", { method: "POST", body: form });
      if (!result?.ok) throw new Error(responseError(result, "preview_failed"));
      candidate = result as unknown as Candidate;
      tab = "add";
    });
  }

  async function inspectRepository(): Promise<void> {
    selectedFile = null;
    candidate = null;
    await run(async () => {
      const result = await api("/admin/plugins/repository/preview", {
        method: "POST",
        body: JSON.stringify({ url: repositoryUrl.trim(), ref: repositoryRef.trim() }),
      });
      if (!result?.ok) throw new Error(responseError(result, "preview_failed"));
      candidate = result as unknown as Candidate;
    });
  }

  async function trust(): Promise<void> {
    if (!candidate) return;
    await run(async () => {
      const result = await api("/admin/plugins/trust", {
        method: "POST",
        body: JSON.stringify({
          publisher: candidate?.manifest.publisher,
          public_key: publisherKey,
          fingerprint: publisherFingerprint,
        }),
      });
      if (!result?.ok) throw new Error(responseError(result, "trust_failed"));
      if (selectedFile) {
        const form = new FormData();
        form.append("file", selectedFile);
        const verified = await api("/admin/plugins/preview", { method: "POST", body: form });
        if (!verified?.ok) throw new Error(responseError(verified, "preview_failed"));
        candidate = verified as unknown as Candidate;
      } else if (candidate?.source) {
        const verified = await api("/admin/plugins/repository/preview", {
          method: "POST",
          body: JSON.stringify({ url: candidate.source.url, ref: candidate.source.commit }),
        });
        if (!verified?.ok) throw new Error(responseError(verified, "preview_failed"));
        candidate = verified as unknown as Candidate;
      }
    });
  }

  async function install(): Promise<void> {
    if ((!selectedFile && !candidate?.source) || !candidate?.trusted) return;
    await run(async () => {
      let staged: unknown;
      if (selectedFile) {
        const form = new FormData();
        form.append("file", selectedFile);
        staged = await api("/admin/plugins/stage", { method: "POST", body: form });
      } else {
        staged = await api("/admin/plugins/repository/stage", {
          method: "POST",
          body: JSON.stringify({ url: candidate?.source?.url, ref: candidate?.source?.commit }),
        });
      }
      if (!staged || typeof staged !== "object" || !("ok" in staged) || !staged.ok)
        throw new Error(responseError(staged, "stage_failed"));
      const selected = staged as unknown as Candidate;
      if (selected.digest !== candidate?.digest || !selected.operation_id)
        throw new Error("candidate_changed");
      const installedResult = await api("/admin/plugins/install", {
        method: "POST",
        body: JSON.stringify({
          operation_id: selected.operation_id,
          digest: selected.digest,
          generation: inventory.generation,
        }),
      });
      if (!installedResult?.ok) throw new Error(responseError(installedResult, "install_failed"));
      candidate = null;
      selectedFile = null;
      tab = "installed";
      await load();
    });
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
  <AdminListToolbar>
    {#snippet actions()}
      <AdminButton onclick={() => (tab = "installed")}
        >{at("plugins_installed", {}, "Installed")}</AdminButton
      >
      <AdminButton onclick={() => (tab = "add")}>{at("plugins_add", {}, "Add plugin")}</AdminButton>
      <AdminButton onclick={() => (tab = "operations")}
        >{at("plugins_operations", {}, "Operations")}</AdminButton
      >
      <AdminButton onclick={() => void run(load)} disabled={busy}
        ><RefreshCw size={14} />{at("btn_refresh", {}, "Refresh")}</AdminButton
      >
    {/snippet}
  </AdminListToolbar>

  {#if error}<p class="admin-error" role="alert">{error}</p>{/if}

  {#if tab === "installed"}
    {#if !installed.length && !inventory.bundled.length}
      <AdminEmptyState>{at("plugins_empty", {}, "No plugins are installed.")}</AdminEmptyState>
    {/if}
    {#each inventory.bundled as plugin (plugin.id)}
      <article class="admin-card plugin-card">
        <strong>{plugin.id}</strong>
        <AdminBadge>{at("plugins_managed_by_image", {}, "Managed by image")}</AdminBadge>
      </article>
    {/each}
    {#each installed as [id, plugin] (id)}
      <article class="admin-card plugin-card">
        <div><strong>{id}</strong> <span>{plugin.version}</span></div>
        <p>{at("plugins_publisher", {}, "Publisher")}: {plugin.publisher}</p>
        <p>
          {at("plugins_state", {}, "State")}: {plugin.enabled
            ? at("plugins_enabled", {}, "Enabled")
            : at("plugins_disabled", {}, "Disabled")} · {plugin.status}
        </p>
        <p class="plugin-digest">SHA-256: {plugin.digest}</p>
        <AdminButton disabled={busy} onclick={() => void toggle(id, !plugin.enabled)}>
          {plugin.enabled
            ? at("plugins_disable", {}, "Disable")
            : at("plugins_enable", {}, "Enable")}
        </AdminButton>
        {#if !plugin.enabled && plugin.source?.kind !== "image"}
          <AdminButton disabled={busy} onclick={() => void remove(id)}>
            {at("plugins_remove", {}, "Remove package")}
          </AdminButton>
        {/if}
      </article>
    {/each}
  {:else if tab === "add"}
    <article class="admin-card plugin-add">
      <h3>{at("plugins_upload_title", {}, "Install a verified package")}</h3>
      <p>
        {at(
          "plugins_execution_warning",
          {},
          "A server plugin runs code with the application's privileges. Install packages only from publishers you trust."
        )}
      </p>
      <AdminButton onclick={() => fileInput?.click()} disabled={busy}
        ><Upload size={14} />{at("plugins_choose_zip", {}, "Choose ZIP")}</AdminButton
      >
      <FileInput
        bind:element={fileInput}
        accept=".zip,application/zip"
        onchange={(event) => {
          const file = event.currentTarget.files?.[0];
          if (file) void inspect(file);
          event.currentTarget.value = "";
        }}
      />
      <p>
        {at(
          "plugins_repository_hint",
          {},
          "Public GitHub or GitLab repository with a ready package index"
        )}
      </p>
      <Input
        bind:value={repositoryUrl}
        aria-label={at("plugins_repository_url", {}, "Repository URL")}
        placeholder="https://github.com/owner/repository"
      />
      <Input
        bind:value={repositoryRef}
        aria-label={at("plugins_repository_ref", {}, "Branch, tag or commit (optional)")}
        placeholder={at("plugins_repository_ref", {}, "Branch, tag or commit (optional)")}
      />
      <AdminButton onclick={() => void inspectRepository()} disabled={busy || !repositoryUrl.trim()}
        >{at("plugins_check_repository", {}, "Check repository")}</AdminButton
      >
      {#if candidate}
        <div class="plugin-candidate">
          <h4>{candidate.manifest.name || candidate.manifest.id} · {candidate.manifest.version}</h4>
          <p>{candidate.manifest.description || ""}</p>
          <p>{at("plugins_publisher", {}, "Publisher")}: {candidate.manifest.publisher}</p>
          <p>SHA-256: {candidate.digest}</p>
          {#if candidate.source}
            <p>{candidate.source.url} · {candidate.source.commit}</p>
          {/if}
          {#if !candidate.trusted}
            <p role="alert">{explain(candidate.trust_reason)}</p>
            <Input
              bind:value={publisherKey}
              aria-label={at("plugins_public_key", {}, "Publisher public key")}
              placeholder={at("plugins_public_key", {}, "Publisher public key")}
            />
            <Input
              bind:value={publisherFingerprint}
              aria-label={at("plugins_fingerprint", {}, "Expected SHA-256 fingerprint")}
              placeholder={at("plugins_fingerprint", {}, "Expected SHA-256 fingerprint")}
            />
            <AdminButton
              onclick={() => void trust()}
              disabled={busy || !publisherKey || !publisherFingerprint}
              >{at("plugins_trust", {}, "Trust publisher")}</AdminButton
            >
          {:else}
            <AdminBadge>{at("plugins_signature_verified", {}, "Signature verified")}</AdminBadge>
            <AdminButton onclick={() => void install()} disabled={busy}
              ><Plus size={14} />{at("plugins_install", {}, "Install disabled")}</AdminButton
            >
          {/if}
        </div>
      {/if}
    </article>
  {:else}
    <article class="admin-card">
      {#each inventory.operations.slice().reverse() as operation (operation.id)}
        <p>{operation.action} · {operation.plugin} · {operation.id}</p>
      {:else}
        <AdminEmptyState>{at("plugins_no_operations", {}, "No operations yet.")}</AdminEmptyState>
      {/each}
    </article>
  {/if}
</div>

<style>
  .plugins-section {
    display: grid;
    gap: 1rem;
  }
  .plugin-card,
  .plugin-add {
    display: grid;
    gap: 0.65rem;
    padding: 1rem;
  }
  .plugin-card p,
  .plugin-add p {
    margin: 0;
  }
  .plugin-digest {
    overflow-wrap: anywhere;
    font-size: 0.8rem;
    opacity: 0.7;
  }
  .plugin-candidate {
    display: grid;
    gap: 0.65rem;
    margin-top: 1rem;
  }
</style>
