<script lang="ts">
  import { focusFirstDialogControl } from "$lib/components/dialogFocusTrap";
  import { getThemesStore } from "$lib/admin/context";
  import {
    normalizeThemeImportFailure,
    themeImportRecommendations,
  } from "$lib/admin/themeImportReport";
  import {
    AdminBadge,
    AdminButton,
    AdminField,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import { Checkbox, Dialog, FileInput, Input } from "$components/ui/index.js";
  import {
    ArrowLeft,
    Check,
    Eye,
    FileText,
    Globe2,
    TriangleAlert,
    Upload,
  } from "$components/ui/icons.js";
  import AppearanceThemePreview from "./AppearanceThemePreview.svelte";
  let {
    at,
    open,
    onclose,
    currentLang = "ru",
    initialRepository = "",
    initialRef = "",
    initialSubdir = "",
  }: {
    at: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
    open: boolean;
    onclose: () => void;
    currentLang?: string;
    initialRepository?: string;
    initialRef?: string;
    initialSubdir?: string;
  } = $props();
  const library = getThemesStore().library;
  const demo =
    typeof window !== "undefined" && window.location.pathname.startsWith("/demo/runtime/");
  let importLayout = $state<HTMLElement | null>(null);
  let method = $state<"archive" | "repository">("archive");
  let repository = $state("");
  let revision = $state("");
  let subdir = $state("");
  let fileInput = $state<HTMLInputElement | null>(null);
  let error = $state("");
  let dragging = $state(false);
  let selected = $state<string[]>([]);
  let conflict = $state("skip");
  let adoption = $state(false);
  let previewUrl = $state("");
  let previewKey = $state("");
  let previewTitle = $state("");
  let previewOpen = $state(false);
  let previewLoading = $state(false);
  const operation = $derived(library.operation);
  const review = $derived(operation?.state === "ready");
  const failureReport = $derived(
    library.failure
      ? {
          ...library.failure,
          title: library.message({ error: library.failure.code }),
          recommendations: themeImportRecommendations(library.failure.code, at),
        }
      : null
  );
  const candidates = $derived(operation?.candidates || []);
  const installedKeys = $derived(library.installations.map((item) => item.key));
  const choices = $derived(
    selected
      .filter((key) => {
        const candidate = candidates.find((item) => item.key === key);
        const existing = library.installations.find((item) => item.key === key);
        return (
          candidate &&
          !candidate.error &&
          (!existing || (conflict === "update" && (existing.managed || adoption)))
        );
      })
      .map((key) => ({
        key,
        action: installedKeys.includes(key)
          ? library.installations.find((item) => item.key === key)?.managed
            ? ("update" as const)
            : ("adopt" as const)
          : ("install" as const),
      }))
  );
  $effect(() => {
    if (open) {
      repository = initialRepository;
      method = initialRepository ? "repository" : "archive";
      error = "";
      revision = initialRef;
      subdir = initialSubdir;
      conflict = "skip";
      adoption = false;
    }
  });
  $effect(() => {
    selected = candidates.filter((item) => !item.error && item.key).map((item) => item.key || "");
  });
  $effect(() => {
    void review;
    if (open) focusFirstDialogControl(() => importLayout);
  });
  async function inspectFile(file?: File) {
    if (!file || library.busy) return;
    error = "";
    await library.inspect(file);
  }
  async function inspectRepository() {
    error = "";
    try {
      const url = new URL(repository.trim());
      if (
        url.protocol !== "https:" ||
        !["github.com", "gitlab.com"].includes(url.hostname) ||
        url.username ||
        url.password ||
        url.port
      )
        throw new Error();
      await library.inspect({
        url: repository.trim(),
        ref: revision.trim(),
        subdir: subdir.trim(),
      });
    } catch {
      error = at(
        "appearance_demo_url_error",
        {},
        "Enter an HTTPS link to a public GitHub or GitLab repository."
      );
    }
  }
  async function close() {
    closePreview();
    await library.cancel();
    onclose();
  }
  function candidateTitle(theme: (typeof candidates)[number], index: number): string {
    return (
      theme.theme?.names?.[currentLang] ||
      theme.theme?.names?.en ||
      theme.theme?.names?.ru ||
      theme.key ||
      theme.path ||
      String(index)
    );
  }
  function clearPreviewUrl() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = "";
  }
  async function preview(theme: (typeof candidates)[number], index: number) {
    clearPreviewUrl();
    previewKey = theme.key || "";
    previewTitle = candidateTitle(theme, index);
    previewOpen = true;
    previewLoading = Boolean(theme.metadata?.preview);
    if (!previewLoading) return;
    try {
      if (operation) previewUrl = await library.preview(previewKey, "dark", operation.id);
    } catch (cause) {
      error = library.message(cause);
    } finally {
      previewLoading = false;
    }
  }
  function closePreview() {
    clearPreviewUrl();
    previewOpen = false;
    previewKey = "";
    previewTitle = "";
    previewLoading = false;
  }
</script>

<Dialog
  {open}
  title={at("appearance_demo_add", {}, "Add themes")}
  closeLabel={at("close", {}, "Close")}
  onclose={close}
  class="admin-dialog appearance-import-dialog"
>
  <div class="import-layout" bind:this={importLayout}>
    <div class="import-steps">
      <span class:current={!review}>1 · {at("appearance_demo_source", {}, "Source")}</span>
      <span class="step-line"></span><span class:current={review}
        >2 · {at("appearance_demo_review", {}, "Review and install")}</span
      >
    </div>
    {#if !review}
      <div class="method-buttons">
        <AdminButton
          disabled={library.busy}
          variant={method === "archive" ? "primary" : "default"}
          aria-pressed={method === "archive"}
          onclick={() => {
            method = "archive";
          }}><Upload size={15} />{at("appearance_demo_archive", {}, "ZIP archive")}</AdminButton
        >
        <AdminButton
          disabled={library.busy}
          variant={method === "repository" ? "primary" : "default"}
          aria-pressed={method === "repository"}
          onclick={() => {
            method = "repository";
          }}
          ><Globe2 size={15} />{at("appearance_demo_repository", {}, "Git repository")}</AdminButton
        >
      </div>
      {#if method === "archive"}
        <section
          class="import-drop"
          class:dragging
          aria-label={at("appearance_demo_drop", {}, "Drop an archive here")}
          ondragover={(event) => {
            event.preventDefault();
            dragging = true;
          }}
          ondragleave={() => {
            dragging = false;
          }}
          ondrop={(event) => {
            event.preventDefault();
            dragging = false;
            if (event.dataTransfer?.files.length !== 1) {
              error = at("appearance_demo_one_file", {}, "Choose one archive.");
              return;
            }
            void inspectFile(event.dataTransfer.files[0]);
          }}
        >
          <span class="upload-symbol"><Upload size={26} /></span>
          <strong>{at("appearance_demo_drop", {}, "Drop an archive here")}</strong>
          <p>
            {at(
              "appearance_demo_drop_hint",
              {},
              "One theme or a whole collection. ZIP, up to 20 MB."
            )}
          </p>
          <FileInput
            bind:element={fileInput}
            class="appearance-import-file"
            accept=".zip,application/zip"
            disabled={library.busy}
            onchange={(event) => {
              void inspectFile(event.currentTarget.files?.[0]);
              event.currentTarget.value = "";
            }}
          />
          <AdminButton disabled={library.busy} onclick={() => fileInput?.click()}
            >{at("appearance_demo_choose_file", {}, "Choose file")}</AdminButton
          >
        </section>
        {#if demo}<AdminButton
            disabled={library.busy}
            onclick={async () => {
              const response = await fetch("/demo/theme-examples.zip");
              if (response.ok)
                await inspectFile(new File([await response.blob()], "theme-examples.zip"));
            }}>{at("appearance_demo_sample", {}, "Try a sample collection")}</AdminButton
          >{/if}
      {:else}
        <AdminField
          label={at("appearance_demo_repo_url", {}, "Repository link")}
          hint={at(
            "appearance_demo_repo_hint",
            {},
            "Public GitHub or GitLab repository with one or more themes."
          )}
          ><Input
            type="url"
            class="input"
            bind:value={repository}
            placeholder="https://github.com/author/themes"
            disabled={library.busy}
          /></AdminField
        >
        <AdminField label={at("appearance_demo_revision", {}, "Branch, tag or commit (optional)")}
          ><Input
            class="input"
            bind:value={revision}
            placeholder="v1.0.0"
            disabled={library.busy}
          /></AdminField
        >
        <AdminField label={at("appearance_subdir", {}, "Theme directory (optional)")}
          ><Input
            class="input"
            bind:value={subdir}
            placeholder="themes"
            disabled={library.busy}
          /></AdminField
        >
        <AdminButton
          variant="primary"
          disabled={library.busy || !repository.trim()}
          onclick={inspectRepository}
          ><Globe2 size={15} />{at("appearance_demo_find", {}, "Find themes")}</AdminButton
        >
      {/if}
      {#if library.busy}<p role="status">
          {at("appearance_import_working", {}, "Downloading and checking the themes…")}
        </p>{/if}
    {:else}
      <div class="source-summary">
        <FileText size={20} />
        <div>
          <strong>{operation?.source?.label}</strong><small
            >{at(
              "appearance_found_count",
              { count: candidates.length },
              "Themes found: {count}"
            )}</small
          ><small>{operation?.source?.commit?.slice(0, 12)}</small>
        </div>
      </div>
      <div class="import-candidates">
        {#each candidates as theme, index (theme.path)}
          {@const candidateFailure = normalizeThemeImportFailure({
            error: theme.error,
            detail: theme.detail,
          })}
          <div class="import-candidate">
            <Checkbox
              disabled={Boolean(theme.error) || library.busy}
              checked={selected.includes(theme.key || "")}
              onCheckedChange={(checked) => {
                selected = checked
                  ? [...selected, theme.key || ""]
                  : selected.filter((key) => key !== theme.key);
              }}
              ariaLabel={theme.theme?.names?.[currentLang] ||
                theme.theme?.names?.en ||
                theme.theme?.names?.ru ||
                theme.key ||
                theme.path}
            />
            <span class="candidate-name"
              ><strong
                >{theme.theme?.names?.[currentLang] ||
                  theme.theme?.names?.en ||
                  theme.theme?.names?.ru ||
                  theme.theme?.names?.en ||
                  theme.key ||
                  theme.path}</strong
              ><small
                >{theme.metadata?.version || at("appearance_unversioned", {}, "Unversioned")} · {theme.files ||
                  0}
                {at("appearance_files", {}, "files")}</small
              >
              {#if candidateFailure}<small role="status">{library.message(candidateFailure)}</small>
                {#if candidateFailure.detail}<small class="candidate-error-detail"
                    >{candidateFailure.detail}</small
                  >{/if}
                <small class="candidate-error-help"
                  >{themeImportRecommendations(candidateFailure.code, at)[0]}</small
                >{/if}
              {#if theme.warnings?.length}<small
                  >{at(
                    "appearance_legacy_package",
                    {},
                    "No package metadata. Ask the author to add a version and license."
                  )}</small
                >{/if}
            </span>
            <AdminBadge
              variant={theme.error
                ? "danger"
                : installedKeys.includes(theme.key || "")
                  ? "warning"
                  : "success"}
              >{theme.error
                ? at("appearance_invalid", {}, "Unavailable")
                : installedKeys.includes(theme.key || "")
                  ? at("appearance_demo_installed", {}, "Installed")
                  : at("appearance_demo_new", {}, "New")}</AdminBadge
            >
            {#if !theme.error}<AdminButton
                size="sm"
                variant="icon"
                aria-label={at("appearance_demo_preview", {}, "Preview") +
                  " " +
                  (theme.key || index)}
                onclick={() => preview(theme, index)}><Eye size={14} /></AdminButton
              >{/if}
          </div>
        {/each}
      </div>
      {#if candidates.some((item) => installedKeys.includes(item.key || "") && !item.error)}
        <AdminField label={at("appearance_demo_conflict", {}, "If a theme is already installed")}
          ><AdminSelect
            value={conflict}
            onValueChange={(value) => {
              conflict = value;
            }}
            ariaLabel={at("appearance_demo_conflict", {}, "If a theme is already installed")}
            items={[
              { value: "skip", label: at("appearance_demo_skip", {}, "Skip existing themes") },
              {
                value: "update",
                label: at("appearance_demo_update", {}, "Update and keep my settings"),
              },
            ]}
          /></AdminField
        >
        {#if candidates.some( (item) => library.installations.some((existing) => existing.key === item.key && !existing.managed && !existing.protected) )}
          <label class="import-candidate"
            ><Checkbox
              checked={adoption}
              onCheckedChange={(value) => {
                adoption = value;
              }}
            /><span
              >{at(
                "appearance_adopt_confirm",
                {},
                "Manage existing server themes through the library. Keep my current settings and track future updates."
              )}</span
            ></label
          >
        {/if}
      {/if}
      <p class="import-note">
        <Check size={16} />{at(
          "appearance_demo_no_activate",
          {},
          "Installation keeps the current theme active. You can preview new themes first."
        )}
      </p>
    {/if}
    {#if failureReport}<section class="import-failure-report" role="alert">
        <header><TriangleAlert size={19} /><strong>{failureReport.title}</strong></header>
        <dl>
          <div>
            <dt>{at("appearance_import_error_code", {}, "Error code")}</dt>
            <dd><code>{failureReport.code}</code></dd>
          </div>
          {#if failureReport.detail}<div>
              <dt>{at("appearance_import_error_detail", {}, "What failed")}</dt>
              <dd>{failureReport.detail}</dd>
            </div>{/if}
        </dl>
        <strong>{at("appearance_import_recommendations", {}, "How to fix it")}</strong>
        <ul>
          {#each failureReport.recommendations as recommendation}
            <li>{recommendation}</li>
          {/each}
        </ul>
      </section>{:else if error || library.error}<p class="import-error" role="alert">
        {error || library.error}
      </p>{/if}
    {#if demo}<p class="demo-disclaimer">
        {at(
          "appearance_demo_import_notice",
          {},
          "Demo imports use sample data and do not access repositories."
        )}
      </p>{/if}
    <footer class="import-footer">
      {#if review}<AdminButton disabled={library.busy} onclick={library.cancel}
          ><ArrowLeft size={14} />{at("back", {}, "Back")}</AdminButton
        >{:else}<AdminButton onclick={close}>{at("cancel", {}, "Cancel")}</AdminButton>{/if}
      {#if review}<AdminButton
          variant="primary"
          disabled={library.busy || !choices.length}
          onclick={async () => {
            if (await library.install(choices)) onclose();
          }}
          ><Upload size={14} />{at(
            "appearance_demo_install",
            { count: choices.length },
            "Install ({count})"
          )}</AdminButton
        >{/if}
    </footer>
  </div>
</Dialog>
<Dialog
  open={previewOpen}
  title={at("appearance_demo_preview_named", { theme: previewTitle }, "Preview {theme}")}
  closeLabel={at("close", {}, "Close")}
  onclose={closePreview}
  class="admin-dialog appearance-preview-dialog"
>
  {#if previewLoading}<p class="preview-loading" role="status">
      {at("appearance_preview_loading", {}, "Loading preview image…")}
    </p>{:else}<AppearanceThemePreview
      url={previewUrl}
      themeKey={previewKey}
      title={previewTitle}
      emptyText={at(
        "appearance_import_no_preview",
        {},
        "This theme does not include a preview image."
      )}
      {at}
    />{/if}
</Dialog>

<style>
  :global(.appearance-import-dialog) {
    width: min(620px, calc(100vw - 24px));
  }
  :global(.appearance-import-file) {
    display: none;
  }
  .import-layout {
    display: grid;
    gap: 20px;
    min-width: 0;
    color: var(--admin-text);
  }
  .import-steps {
    display: flex;
    align-items: center;
    gap: 14px;
    font-size: 12px;
    color: var(--admin-muted);
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
  .method-buttons {
    display: flex;
    gap: 8px;
  }
  .method-buttons :global(button) {
    flex: 1;
  }
  .import-drop {
    display: grid;
    justify-items: center;
    gap: 13px;
    padding: 32px 16px;
    border: 1px dashed var(--admin-border-strong);
    border-radius: 12px;
    background: var(--admin-surface-2);
    text-align: center;
  }
  .dragging {
    border-color: var(--accent);
  }
  .upload-symbol {
    display: grid;
    place-items: center;
    width: 54px;
    height: 54px;
    border-radius: 15px;
    background: var(--admin-surface);
    color: var(--accent);
    border: 1px solid var(--admin-border);
  }
  p {
    margin: 0;
    font-size: 12px;
    line-height: 1.6;
    color: var(--admin-muted);
  }
  .source-summary {
    display: flex;
    gap: 12px;
    align-items: center;
    min-width: 0;
  }
  .source-summary div {
    min-width: 0;
  }
  .source-summary strong {
    overflow-wrap: anywhere;
    font-size: 13px;
  }
  strong,
  small {
    display: block;
  }
  small {
    color: var(--admin-muted);
    margin-top: 3px;
    font-size: 11px;
  }
  .import-candidates {
    border: 1px solid var(--admin-border);
    border-radius: 10px;
    overflow: hidden;
  }
  .import-candidate {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px;
    cursor: pointer;
  }
  .import-candidate + .import-candidate {
    border-top: 1px solid var(--admin-border);
  }
  .candidate-name {
    flex: 1;
    font-size: 13px;
  }
  .import-note {
    display: flex;
    align-items: start;
    gap: 8px;
  }
  .import-note :global(svg) {
    flex-shrink: 0;
    margin-top: 3px;
  }
  .demo-disclaimer {
    padding: 11px 13px;
    border-radius: 8px;
    background: var(--admin-surface-2);
    font-size: 11px;
  }
  .import-footer {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    padding-top: 16px;
    border-top: 1px solid var(--admin-border);
  }
  .import-error {
    color: var(--danger);
  }
  .preview-loading {
    min-height: min(70vh, 560px);
    display: grid;
    place-items: center;
  }
  .import-failure-report {
    display: grid;
    gap: 12px;
    padding: 14px;
    border: 1px solid color-mix(in srgb, var(--danger) 48%, var(--admin-border));
    border-radius: 10px;
    background: color-mix(in srgb, var(--danger) 8%, var(--admin-surface-2));
    font-size: 12px;
    line-height: 1.5;
  }
  .import-failure-report header {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--danger);
  }
  .import-failure-report dl,
  .import-failure-report ul {
    margin: 0;
  }
  .import-failure-report dl {
    display: grid;
    gap: 8px;
  }
  .import-failure-report dl div {
    display: grid;
    grid-template-columns: minmax(90px, 0.28fr) 1fr;
    gap: 10px;
  }
  .import-failure-report dt {
    color: var(--admin-muted);
  }
  .import-failure-report dd {
    min-width: 0;
    margin: 0;
    overflow-wrap: anywhere;
  }
  .import-failure-report code {
    color: var(--admin-text);
  }
  .import-failure-report ul {
    display: grid;
    gap: 5px;
    padding-left: 18px;
  }
  .candidate-error-detail,
  .candidate-error-help {
    overflow-wrap: anywhere;
  }
  .candidate-error-detail {
    color: var(--danger);
  }
  @media (max-width: 480px) {
    .import-layout {
      gap: 16px;
    }
    .import-drop {
      padding: 22px 12px;
    }
    .import-candidate {
      gap: 9px;
      padding: 12px;
    }
    .method-buttons :global(button) {
      padding-inline: 10px;
    }
    .import-steps {
      gap: 7px;
      font-size: 11px;
    }
  }
</style>
