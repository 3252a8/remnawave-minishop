<script lang="ts">
  import { focusFirstDialogControl } from "$lib/components/dialogFocusTrap";
  import AdminImportSource from "$components/patterns/admin/AdminImportSource.svelte";
  import { AdminBadge, AdminButton } from "$components/patterns/admin/index.js";
  import { Dialog } from "$components/ui/index.js";
  import { ArrowLeft, Check, Upload } from "$components/ui/icons.js";
  import type { AdminApi } from "../adminStores";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Candidate = {
    operation_id?: string;
    digest: string;
    manifest: {
      id: string;
      version: string;
      publisher: string;
      publisher_fingerprint: string;
      publisher_public_key?: string;
      name?: string;
      description?: string;
    };
    trusted: boolean;
    trust_reason: string;
    source?: { url: string; ref: string; commit: string; artifact: string };
  };

  let {
    api,
    at,
    open,
    generation,
    initialRepository = "",
    initialRef = "",
    onclose,
    oninstalled,
  }: {
    api: AdminApi;
    at: TranslateFn;
    open: boolean;
    generation: number;
    initialRepository?: string;
    initialRef?: string;
    onclose: () => void;
    oninstalled: () => void | Promise<void>;
  } = $props();

  let layout = $state<HTMLElement | null>(null);
  let method = $state<"archive" | "repository">("archive");
  let repository = $state("");
  let revision = $state("");
  let candidate = $state<Candidate | null>(null);
  let selectedFile = $state<File | null>(null);
  let busy = $state(false);
  let error = $state("");

  const sourceLabels = $derived({
    archive: at("appearance_demo_archive", {}, "ZIP archive"),
    repository: at("appearance_demo_repository", {}, "Git repository"),
    drop: at("plugins_drop", {}, "Drop a plugin ZIP here"),
    dropHint: at("plugins_drop_hint", {}, "One signed plugin package. ZIP, up to 96 MiB."),
    chooseFile: at("plugins_choose_zip", {}, "Choose ZIP"),
    oneFile: at("plugins_one_file", {}, "Choose one archive."),
    repositoryUrl: at("plugins_repository_url", {}, "Repository URL"),
    repositoryHint: at(
      "plugins_repository_hint",
      {},
      "Public GitHub or GitLab repository with a ready package index"
    ),
    revision: at("plugins_repository_ref", {}, "Branch, tag or commit (optional)"),
    find: at("plugins_check_repository", {}, "Check repository"),
  });

  $effect(() => {
    if (open) {
      method = initialRepository ? "repository" : "archive";
      repository = initialRepository;
      revision = initialRef;
      candidate = null;
      selectedFile = null;
      error = "";
      focusFirstDialogControl(() => layout);
    }
  });

  function responseError(value: unknown, fallback: string): string {
    if (value && typeof value === "object" && "error" in value && typeof value.error === "string")
      return value.error;
    return fallback;
  }

  function explain(code: string): string {
    const messages: Record<string, string> = {
      publisher_not_trusted: at(
        "plugins_publisher_not_trusted",
        {},
        "Trust this publisher before installing."
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
      candidate_changed: at(
        "plugins_candidate_changed",
        {},
        "The package changed. Review it again."
      ),
      incompatible_core_version: at(
        "plugins_incompatible_core_version",
        {},
        "This plugin requires a newer Minishop version."
      ),
    };
    return messages[code] || code.replaceAll("_", " ");
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

  async function inspectFile(file: File): Promise<void> {
    await run(async () => {
      candidate = null;
      selectedFile = file;
      const form = new FormData();
      form.append("file", file);
      const result = await api("/admin/plugins/preview", { method: "POST", body: form });
      if (!result?.ok) throw new Error(responseError(result, "preview_failed"));
      candidate = result as unknown as Candidate;
    });
  }

  async function inspectRepository(): Promise<void> {
    await run(async () => {
      candidate = null;
      selectedFile = null;
      const result = await api("/admin/plugins/repository/preview", {
        method: "POST",
        body: JSON.stringify({ url: repository.trim(), ref: revision.trim() }),
      });
      if (!result?.ok) throw new Error(responseError(result, "preview_failed"));
      candidate = result as unknown as Candidate;
    });
  }

  async function install(): Promise<void> {
    if (
      (!selectedFile && !candidate?.source) ||
      (!candidate?.trusted && !candidate?.manifest.publisher_public_key)
    )
      return;
    await run(async () => {
      if (!candidate?.trusted) {
        const trusted = await api("/admin/plugins/trust", {
          method: "POST",
          body: JSON.stringify({
            publisher: candidate?.manifest.publisher,
            public_key: candidate?.manifest.publisher_public_key,
            fingerprint: candidate?.manifest.publisher_fingerprint,
          }),
        });
        if (!trusted?.ok) throw new Error(responseError(trusted, "trust_failed"));
      }
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
      const result = await api("/admin/plugins/install", {
        method: "POST",
        body: JSON.stringify({
          operation_id: selected.operation_id,
          digest: selected.digest,
          generation,
        }),
      });
      if (!result?.ok) throw new Error(responseError(result, "install_failed"));
      onclose();
      await oninstalled();
    });
  }
</script>

<Dialog
  {open}
  title={at("plugins_add", {}, "Add plugin")}
  closeLabel={at("close", {}, "Close")}
  {onclose}
  class="admin-dialog plugin-import-dialog"
>
  <div class="import-layout" bind:this={layout}>
    <div class="import-steps">
      <span class:current={!candidate}>1 · {at("plugins_source", {}, "Source")}</span>
      <span class="step-line"></span>
      <span class:current={Boolean(candidate)}
        >2 · {at("plugins_review", {}, "Review and install")}</span
      >
    </div>
    {#if !candidate}
      <AdminImportSource
        bind:method
        bind:repository
        bind:revision
        labels={sourceLabels}
        {busy}
        onarchive={inspectFile}
        onrepository={inspectRepository}
        onerror={(message) => (error = message)}
      />
      <p class="import-note">
        {at(
          "plugins_execution_warning",
          {},
          "A server plugin runs code with the application's privileges. Install packages only from publishers you trust."
        )}
      </p>
    {:else}
      <div class="candidate-card">
        <div class="candidate-heading">
          <div>
            <h3>{candidate.manifest.name || candidate.manifest.id}</h3>
            <small>{candidate.manifest.id} · {candidate.manifest.version}</small>
          </div>
          <AdminBadge variant={candidate.trusted ? "success" : "warning"}>
            {candidate.trusted
              ? at("plugins_signature_verified", {}, "Signature verified")
              : candidate.manifest.publisher_public_key
                ? at("plugins_new_publisher", {}, "New publisher")
                : at("plugins_trust_required", {}, "Publisher key required")}
          </AdminBadge>
        </div>
        {#if candidate.manifest.description}<p>{candidate.manifest.description}</p>{/if}
        <dl>
          <div>
            <dt>{at("plugins_publisher", {}, "Publisher")}</dt>
            <dd>{candidate.manifest.publisher}</dd>
          </div>
          <div>
            <dt>{at("plugins_zip_sha256", {}, "ZIP SHA-256")}</dt>
            <dd class="digest">{candidate.digest}</dd>
          </div>
          {#if candidate.source}
            <div>
              <dt>{at("plugins_source", {}, "Source")}</dt>
              <dd>{candidate.source.url}<br />{candidate.source.commit}</dd>
            </div>
          {/if}
        </dl>
      </div>
      {#if !candidate.trusted}
        {#if candidate.manifest.publisher_public_key}
          <p class="import-note" role="status">{explain(candidate.trust_reason)}</p>
          <p class="import-note">
            {at(
              "plugins_digest_hint",
              {},
              "Compare the ZIP SHA-256 above with the value published by the plugin author. Installing will trust this publisher for future updates."
            )}
          </p>
        {:else}
          <p class="import-note" role="alert">
            {at(
              "plugins_legacy_key_missing",
              {},
              "This ZIP does not include a publisher key. Ask its author for a current package."
            )}
          </p>
        {/if}
      {:else}
        <p class="import-note">
          <Check size={16} />{at(
            "plugins_install_note",
            {},
            "The package is installed disabled. Enable it from the library after review."
          )}
        </p>
      {/if}
    {/if}
    {#if busy}<p role="status">{at("plugins_working", {}, "Checking the package…")}</p>{/if}
    {#if error}<p class="import-error" role="alert">{error}</p>{/if}
    <footer class="import-footer">
      {#if candidate}
        <AdminButton disabled={busy} onclick={() => (candidate = null)}
          ><ArrowLeft size={14} />{at("back", {}, "Back")}</AdminButton
        >
      {:else}
        <AdminButton onclick={onclose}>{at("cancel", {}, "Cancel")}</AdminButton>
      {/if}
      {#if candidate?.trusted || candidate?.manifest.publisher_public_key}
        <AdminButton variant="primary" disabled={busy} onclick={install}
          ><Upload size={14} />{candidate?.trusted
            ? at("plugins_install", {}, "Install disabled")
            : at(
                "plugins_trust_and_install",
                {},
                "Trust publisher and install disabled"
              )}</AdminButton
        >
      {/if}
    </footer>
  </div>
</Dialog>

<style>
  :global(.plugin-import-dialog) {
    width: min(620px, calc(100vw - 24px));
  }
  .import-layout {
    display: grid;
    gap: 18px;
    min-width: 0;
    color: var(--admin-text);
  }
  .import-steps {
    display: flex;
    align-items: center;
    gap: 14px;
    color: var(--admin-muted);
    font-size: 12px;
  }
  .current {
    color: var(--admin-text);
    font-weight: 650;
  }
  .step-line {
    flex: 1;
    height: 1px;
    background: var(--admin-border);
  }
  .candidate-card {
    display: grid;
    gap: 12px;
    padding: 16px;
    border: 1px solid var(--admin-border);
    border-radius: 12px;
    background: var(--admin-surface-2);
  }
  .candidate-heading {
    display: flex;
    justify-content: space-between;
    align-items: start;
    gap: 12px;
  }
  h3,
  p,
  dl {
    margin: 0;
  }
  h3 {
    font-size: 15px;
  }
  small,
  p,
  dt {
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.6;
  }
  dl {
    display: grid;
    gap: 8px;
  }
  dl > div {
    display: grid;
    grid-template-columns: minmax(78px, 0.25fr) 1fr;
    gap: 8px;
  }
  dd {
    min-width: 0;
    margin: 0;
    font-size: 12px;
    overflow-wrap: anywhere;
  }
  .digest {
    font-family: ui-monospace, monospace;
    font-size: 11px;
  }
  .import-note {
    display: flex;
    align-items: start;
    gap: 8px;
  }
  .import-note :global(svg) {
    flex-shrink: 0;
    margin-top: 2px;
  }
  .import-error {
    color: var(--danger);
  }
  .import-footer {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    padding-top: 16px;
    border-top: 1px solid var(--admin-border);
  }
  @media (max-width: 480px) {
    .import-layout {
      gap: 15px;
    }
    .import-steps {
      gap: 7px;
      font-size: 11px;
    }
    .candidate-heading {
      flex-wrap: wrap;
    }
  }
</style>
