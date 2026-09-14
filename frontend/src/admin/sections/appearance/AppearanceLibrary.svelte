<script lang="ts">
  import type { Snippet } from "svelte";
  import { onMount } from "svelte";
  import { getThemesStore } from "$lib/admin/context";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminListToolbar,
  } from "$components/patterns/admin/index.js";
  import { Checkbox, Dialog, FileInput, Input } from "$components/ui/index.js";
  import {
    Check,
    ExternalLink,
    Eye,
    FileText,
    Plus,
    RotateCcw,
    Settings,
    Trash2,
    Download,
    Save,
    RefreshCw,
    ChevronDown,
  } from "$components/ui/icons.js";
  import type { ThemeEntry } from "$lib/admin/appearanceOptions";
  import type { ThemeInstallation } from "$lib/admin/stores/themeLibraryStore.svelte";
  import AppearanceThemePreview from "./AppearanceThemePreview.svelte";
  import AppearanceImportDialog from "./AppearanceImportDialog.svelte";
  import "./AppearanceLibrary.css";
  type LibraryTheme = {
    entry: ThemeEntry;
    key: string;
    title: string;
    source: string;
    imported: boolean;
    installation?: ThemeInstallation;
  };
  let {
    at,
    themes,
    currentLang = "ru",
    themeTitle,
    defaultEditor,
    brandEditor,
    customEditor,
    behaviorEditor,
    dirty,
    saving = false,
    onsave,
    onpreview,
    oncapture,
  }: {
    at: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
    themes: ThemeEntry[];
    currentLang?: string;
    themeTitle: (theme: ThemeEntry) => string;
    defaultEditor: Snippet;
    brandEditor: Snippet;
    customEditor: Snippet<[string]>;
    behaviorEditor: Snippet;
    dirty: boolean;
    saving?: boolean;
    onsave: () => void | Promise<void>;
    onpreview: (event: MouseEvent, theme: ThemeEntry) => void;
    oncapture: (theme: ThemeEntry) => Promise<void>;
  } = $props();
  const store = getThemesStore();
  const library = store.library;
  const demo =
    typeof window !== "undefined" && window.location.pathname.startsWith("/demo/runtime/");
  const active = $derived(store.savedThemesCatalog.default_theme);
  let query = $state("");
  let importOpen = $state(false);
  let repository = $state("");
  let repositoryRef = $state("");
  let repositorySubdir = $state("");
  let settingsKey = $state("");
  let removal = $state<LibraryTheme | null>(null);
  let exportTheme = $state<LibraryTheme | null>(null);
  let newKey = $state("");
  let includeOverrides = $state(false);
  let guideOpen = $state(false);
  let preferencesOpen = $state(false);
  let captureBusy = $state(false);
  let addCardDragging = $state(false);
  const blocked = $derived(dirty || library.busy || saving || !library.writable);
  const catalog = $derived<LibraryTheme[]>(
    themes.map((theme) => {
      const installation = library.installations.find((item) => item.key === theme.key);
      return {
        entry: theme,
        key: theme.key,
        title: themeTitle(theme),
        imported: installation?.managed || false,
        source:
          installation?.source?.label ||
          at(
            installation?.protected ? "appearance_demo_bundled" : "appearance_legacy",
            {},
            "Installed on server"
          ),
        installation,
      };
    })
  );
  const settings = $derived(catalog.find((theme) => theme.key === settingsKey) || null);
  const filtered = $derived(
    catalog.filter((theme) =>
      (theme.title + " " + theme.key).toLowerCase().includes(query.toLowerCase())
    )
  );
  onMount(() => {
    void library.load();
  });
  async function activate(theme: LibraryTheme) {
    if (blocked) return;
    store.setCurrentTheme(theme.key);
    if (await store.saveThemes()) {
      library.notify(
        at("appearance_demo_active_notice", { theme: theme.title }, "{theme} is now active.")
      );
      await library.load();
    }
  }
  function openImport(url = "", ref = "", subdir = "") {
    repository = url;
    repositoryRef = ref;
    repositorySubdir = subdir;
    importOpen = true;
  }
  async function inspectThemeFile(file?: File): Promise<void> {
    if (!file || blocked) return;
    openImport();
    await library.inspect(file);
  }
</script>

<div class="appearance-library">
  {#if demo}<div class="demo-banner">
      <span
        ><span class="demo-dot"></span>{at(
          "appearance_demo_label",
          {},
          "Interactive concept"
        )}</span
      ><small
        >{at(
          "appearance_demo_local",
          {},
          "Changes in this demo are not saved to the server"
        )}</small
      >
    </div>{/if}
  <AdminListToolbar class="appearance-action-bar">
    {#snippet actions()}
      <AdminButton
        size="sm"
        variant="primary"
        disabled={blocked}
        onclick={() => {
          openImport();
        }}><Plus size={15} />{at("appearance_demo_add", {}, "Add themes")}</AdminButton
      >
      <AdminButton
        size="sm"
        disabled={blocked}
        onclick={() => library.exportThemes(catalog.map((theme) => theme.key))}
        ><Download size={14} />{at(
          "appearance_export_collection",
          {},
          "Download collection"
        )}</AdminButton
      >
      <AdminButton
        size="sm"
        onclick={() => {
          guideOpen = true;
        }}
        ><FileText size={15} />{at(
          "appearance_demo_author_guide",
          {},
          "Create a theme"
        )}</AdminButton
      >
      <AdminButton size="sm" disabled={blocked} onclick={library.refresh}
        ><RefreshCw size={14} />{at("btn_refresh", {}, "Refresh")}</AdminButton
      >
      <AdminButton
        size="sm"
        variant="primary"
        disabled={!dirty || library.busy || saving}
        onclick={onsave}><Save size={14} />{at("btn_save", {}, "Save")}</AdminButton
      >
    {/snippet}
  </AdminListToolbar>
  {#if dirty}<p class="appearance-unsaved-note">
      {at("appearance_unsaved", {}, "Save your changes before managing themes.")}
    </p>{/if}
  {#if library.error}<p class="import-error" role="alert">{library.error}</p>{/if}
  {#if !library.writable}<p class="appearance-settings-note">
      {at(
        "appearance_read_only",
        {},
        "Theme storage is read-only. Check the volume permissions on the server."
      )}
    </p>{/if}
  <section class="appearance-preferences-card">
    <header class="appearance-preferences-header">
      <button
        type="button"
        class="appearance-preferences-trigger"
        aria-expanded={preferencesOpen}
        onclick={() => (preferencesOpen = !preferencesOpen)}
      >
        <span>
          <strong>{at("appearance_preferences_title", {}, "Appearance settings")}</strong>
          <small>{at("appearance_preferences_sub", {}, "Behavior and branding")}</small>
        </span>
        <ChevronDown size={17} />
      </button>
    </header>
    {#if preferencesOpen}
      <div class="appearance-preferences-content" data-state="open">
        {@render behaviorEditor()}
        {@render brandEditor()}
      </div>
    {/if}
  </section>
  <section class="library-section">
    <div class="library-title">
      <h3>{at("appearance_demo_library", {}, "Theme library")}</h3>
      <AdminBadge>{catalog.length}</AdminBadge>
    </div>
    <AdminListToolbar>
      {#snippet search()}
        <Input
          class="input"
          value={query}
          oninput={(event) => {
            query = event.currentTarget.value;
          }}
          placeholder={at("appearance_demo_search", {}, "Search themes")}
          aria-label={at("appearance_demo_search", {}, "Search themes")}
        />
      {/snippet}
    </AdminListToolbar>
    <div class="theme-library-grid">
      {#each filtered as theme (theme.key)}
        <article
          data-theme-key={theme.key}
          class="library-theme-card"
          class:active={active === theme.key}
        >
          <div class="card-preview-wrap">
            <AppearanceThemePreview
              url={theme.installation?.preview_url || ""}
              themeKey={theme.key}
              title={theme.title}
              {at}
            />{#if active === theme.key}<span class="preview-active"
                ><Check size={12} />{at("appearance_demo_active", {}, "Active")}</span
              >{/if}
          </div>
          <div class="theme-card-content">
            <div class="theme-card-title">
              <h4>{theme.title}</h4>
              <AdminBadge
                >{theme.installation?.version ||
                  at(
                    theme.installation?.protected
                      ? "appearance_demo_bundled"
                      : "appearance_unversioned",
                    {},
                    "Unversioned"
                  )}</AdminBadge
              >
            </div>
            <p class="theme-description">
              {theme.installation?.metadata?.description?.[currentLang] ||
                theme.installation?.metadata?.description?.en ||
                theme.installation?.metadata?.description?.ru ||
                (theme.key === "dark"
                  ? at(
                      "appearance_demo_desc_default",
                      {},
                      "The original look. Your colors, fonts and details."
                    )
                  : theme.key === "windows95"
                    ? at(
                        "appearance_demo_desc_windows",
                        {},
                        "Familiar windows, sharp edges and a nostalgic desktop."
                      )
                    : theme.key === "ascii"
                      ? at(
                          "appearance_demo_desc_ascii",
                          {},
                          "Monospace type and a clean terminal aesthetic."
                        )
                      : at(
                          "appearance_demo_desc_imported",
                          {},
                          "A custom theme. Check its appearance in the preview."
                        ))}
            </p>
            <small class="theme-source" title={theme.source}>{theme.source}</small>
            <div class="theme-card-actions">
              <AdminButton
                size="sm"
                onclick={(event) => onpreview(event, theme.entry)}
                aria-label={at(
                  "appearance_demo_preview_named",
                  { theme: theme.title },
                  "Preview {theme}"
                )}><Eye size={14} />{at("appearance_demo_preview", {}, "Preview")}</AdminButton
              ><AdminButton
                size="sm"
                variant={active === theme.key ? "ghost" : "default"}
                disabled={blocked || active === theme.key}
                onclick={() => activate(theme)}
                >{#if active === theme.key}<Check size={14} />{at(
                    "appearance_demo_selected",
                    {},
                    "Selected"
                  )}{:else}{at("appearance_demo_activate", {}, "Activate")}{/if}</AdminButton
              ><AdminButton
                size="sm"
                variant="icon"
                aria-label={at(
                  "appearance_demo_settings_named",
                  { theme: theme.title },
                  "Settings for {theme}"
                )}
                onclick={() => {
                  settingsKey = theme.key;
                }}><Settings size={15} /></AdminButton
              >
            </div>
          </div>
        </article>
      {/each}
      {#if !query}<div
          class="theme-add-card"
          class:dragging={addCardDragging}
          role="button"
          tabindex={blocked ? -1 : 0}
          aria-disabled={blocked}
          aria-label={at("appearance_demo_drop", {}, "Drop an archive here")}
          onclick={() => {
            if (!blocked) openImport();
          }}
          onkeydown={(event) => {
            if (!blocked && (event.key === "Enter" || event.key === " ")) {
              event.preventDefault();
              openImport();
            }
          }}
          ondragover={(event) => {
            event.preventDefault();
            if (!blocked) addCardDragging = true;
          }}
          ondragleave={() => {
            addCardDragging = false;
          }}
          ondrop={(event) => {
            event.preventDefault();
            event.stopPropagation();
            addCardDragging = false;
            if (event.dataTransfer?.files.length === 1) {
              void inspectThemeFile(event.dataTransfer.files[0]);
            }
          }}
        >
          <FileInput
            class="theme-add-file-input"
            accept=".zip,application/zip,application/x-zip-compressed"
            tabindex={-1}
            aria-hidden="true"
            onchange={(event) => {
              void inspectThemeFile(event.currentTarget.files?.[0]);
              event.currentTarget.value = "";
            }}
          /><span class="add-symbol"><Plus size={25} /></span><strong
            >{at("appearance_demo_your_theme", {}, "Room for your idea")}</strong
          ><span
            >{at(
              "appearance_demo_your_theme_hint",
              {},
              "Upload a ZIP or connect a repository with a whole collection."
            )}</span
          ><span class="add-card-link"
            >{at("appearance_demo_add", {}, "Add themes")} <Plus size={14} /></span
          >
        </div>{/if}
    </div>
    {#if !filtered.length}<AdminEmptyState
        >{at(
          "appearance_demo_not_found",
          {},
          "No themes found. Try another name."
        )}</AdminEmptyState
      >{/if}
  </section>
</div>
<AppearanceImportDialog
  {currentLang}
  {at}
  open={importOpen}
  initialRepository={repository}
  initialRef={repositoryRef}
  initialSubdir={repositorySubdir}
  onclose={() => {
    importOpen = false;
  }}
/>

<Dialog
  open={Boolean(settings)}
  title={settings?.title || ""}
  closeLabel={at("close", {}, "Close")}
  onclose={() => {
    settingsKey = "";
  }}
  class="admin-dialog appearance-settings-dialog"
>
  {#if settings}
    {#if settings.key === "dark"}
      {@render defaultEditor()}
    {:else}
      {@render customEditor(settings.key)}
    {/if}
    {#if settings.installation?.metadata?.author}<p class="appearance-settings-note">
        {at(
          "appearance_author",
          { name: settings.installation.metadata.author.name },
          "Author: {name}"
        )}
      </p>{/if}
    {#if settings.installation?.metadata?.license}<p class="appearance-settings-note">
        {at(
          "appearance_license",
          { license: settings.installation.metadata.license },
          "License: {license}"
        )}
      </p>{/if}
    <div class="appearance-settings-footer">
      <div class="appearance-settings-footer-group">
        <AdminButton
          disabled={blocked || captureBusy}
          onclick={async () => {
            if (!settings) return;
            captureBusy = true;
            try {
              await oncapture(settings.entry);
              library.notify(at("appearance_preview_saved", {}, "Preview saved."));
            } catch {
              library.notify(at("appearance_preview_save_failed", {}, "Could not save preview."));
            } finally {
              captureBusy = false;
            }
          }}><Eye size={14} />{at("appearance_capture_preview", {}, "Save preview")}</AdminButton
        >
        <AdminButton
          disabled={blocked}
          onclick={() => {
            exportTheme = settings;
            settingsKey = "";
            newKey = "";
          }}><Download size={14} />{at("appearance_export", {}, "Download")}</AdminButton
        >
      </div>
      <AdminButton
        variant="primary"
        disabled={!dirty || library.busy || store.themesSaving}
        onclick={onsave}
      >
        <Save size={14} />
        {saving ? at("btn_saving", {}, "Saving...") : at("btn_save", {}, "Save")}
      </AdminButton>
      {#if settings.installation?.source?.url}<AdminButton
          disabled={blocked}
          onclick={() => {
            openImport(
              settings?.installation?.source?.url,
              settings?.installation?.source?.ref,
              settings?.installation?.source?.subdir
            );
            settingsKey = "";
          }}>{at("appearance_check_update", {}, "Check for updates")}</AdminButton
        >{/if}
      {#if settings.installation?.can_rollback}<AdminButton
          disabled={blocked}
          onclick={async () => {
            if (settings && (await library.mutate(settings.key, "rollback"))) settingsKey = "";
          }}
          ><RotateCcw size={14} />{at(
            "appearance_rollback",
            {},
            "Restore previous version"
          )}</AdminButton
        >{/if}
    </div>
    <div class="appearance-settings-footer">
      <small>{settings.source}</small>{#if settings.imported}<AdminButton
          variant="dangerSoft"
          disabled={blocked || active === settings.key}
          onclick={() => {
            removal = settings;
            settingsKey = "";
          }}><Trash2 size={14} />{at("appearance_demo_remove", {}, "Remove theme")}</AdminButton
        >{:else}<AdminBadge
          >{at(
            settings.installation?.protected ? "appearance_demo_protected" : "appearance_legacy",
            {},
            "Installed on server"
          )}</AdminBadge
        >{/if}
    </div>
    {#if settings.imported && active === settings.key}<p class="appearance-settings-note">
        {at(
          "appearance_demo_remove_active",
          {},
          "Activate another theme before removing this one."
        )}
      </p>{/if}
  {/if}
</Dialog>
<Dialog
  open={Boolean(removal)}
  title={at("appearance_demo_remove", {}, "Remove theme")}
  closeLabel={at("close", {}, "Close")}
  onclose={() => {
    removal = null;
  }}
  class="admin-dialog admin-dialog-compact"
>
  <p class="appearance-settings-note">
    {at(
      "appearance_demo_remove_confirm",
      { theme: removal?.title || "" },
      "Remove {theme} from the demo library? You can add it again later."
    )}
  </p>
  <div class="appearance-settings-footer">
    <AdminButton
      onclick={() => {
        removal = null;
      }}>{at("cancel", {}, "Cancel")}</AdminButton
    ><AdminButton
      variant="danger"
      disabled={blocked}
      onclick={async () => {
        if (!removal) return;
        const removed = await library.mutate(removal.key, "remove");
        if (removed) {
          removal = null;
        }
      }}>{at("appearance_demo_remove", {}, "Remove theme")}</AdminButton
    >
  </div>
</Dialog>
<Dialog
  open={guideOpen}
  title={at("appearance_demo_author_guide", {}, "Create a theme")}
  closeLabel={at("close", {}, "Close")}
  onclose={() => {
    guideOpen = false;
  }}
  class="admin-dialog admin-dialog-compact"
>
  <div class="appearance-guide">
    <p>
      {at(
        "appearance_demo_guide_intro",
        {},
        "Start with a copy of Default, ASCII or Windows 95. Give your theme a unique key and keep all assets inside its folder."
      )}
    </p>
    <div class="appearance-settings-footer">
      {#each catalog.filter( (theme) => ["dark", "ascii", "windows95"].includes(theme.key) ) as theme}<AdminButton
          onclick={() => {
            exportTheme = theme;
            newKey = "my-" + theme.key;
            guideOpen = false;
          }}>{theme.title}</AdminButton
        >{/each}
    </div>
    <pre>my-theme/
  theme.json
  theme-package.json
  style.css
  assets/
    preview.webp</pre>
    <ol>
      <li>
        {at(
          "appearance_demo_guide_manifest",
          {},
          "Set the name, key and light/dark variants in theme.json."
        )}
      </li>
      <li>
        {at(
          "appearance_demo_guide_zip",
          {},
          "ZIP the theme folder. For a collection, put multiple theme folders in one archive."
        )}
      </li>
      <li>
        {at(
          "appearance_demo_guide_git",
          {},
          "Or publish the folder in a repository. A collection can use a themes/ directory."
        )}
      </li>
    </ol>
    <a
      href="https://dev.minishop.minidoc.cc/features/theme-packages/"
      target="_blank"
      rel="noreferrer"
      >{at("appearance_demo_guide_link", {}, "Current theme format documentation")}<ExternalLink
        size={13}
      /></a
    >
  </div>
</Dialog>

<Dialog
  open={Boolean(exportTheme)}
  title={at("appearance_export", {}, "Download")}
  closeLabel={at("close", {}, "Close")}
  onclose={() => {
    exportTheme = null;
  }}
  class="admin-dialog admin-dialog-compact"
>
  <div class="appearance-guide">
    <p>
      {at(
        "appearance_export_hint",
        {},
        "Leave the key empty to export the original. Enter a unique key to create your own theme."
      )}
    </p>
    <Input
      class="input"
      aria-label={at("appearance_new_key", {}, "New theme key")}
      placeholder="my-theme"
      bind:value={newKey}
    />
    <label
      ><Checkbox
        checked={includeOverrides}
        onCheckedChange={(value) => {
          includeOverrides = value;
        }}
      />{at("appearance_export_overrides", {}, "Include my palette and settings")}</label
    >
    <AdminButton
      variant="primary"
      disabled={library.busy ||
        (Boolean(newKey) &&
          (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(newKey) ||
            catalog.some((theme) => theme.key === newKey)))}
      onclick={async () => {
        if (exportTheme) await library.exportThemes([exportTheme.key], includeOverrides, newKey);
        if (!library.error) exportTheme = null;
      }}><Download size={14} />{at("appearance_download_zip", {}, "Download ZIP")}</AdminButton
    >
  </div>
</Dialog>
