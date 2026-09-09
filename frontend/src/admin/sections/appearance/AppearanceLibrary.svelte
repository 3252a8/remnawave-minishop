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
  import { Accordion, Checkbox, Dialog, Input } from "$components/ui/index.js";
  import {
    Check,
    ChevronDown,
    ExternalLink,
    Eye,
    FileText,
    Monitor,
    Paintbrush,
    Plus,
    RotateCcw,
    Settings,
    Smartphone,
    Trash2,
    Download,
    Save,
    RefreshCw,
  } from "$components/ui/icons.js";
  import type { ThemeEntry } from "$lib/admin/appearanceOptions";
  import type { ThemeInstallation } from "$lib/admin/stores/themeLibraryStore.svelte";
  import AppearanceThemePreview from "./AppearanceThemePreview.svelte";
  import AppearanceImportDialog from "./AppearanceImportDialog.svelte";
  import "./AppearanceLibrary.css";
  type LibraryTheme = {
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
    onsave,
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
    onsave: () => void | Promise<void>;
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
  let preview = $state<LibraryTheme | null>(null);
  let previewMobile = $state(true);
  let previewVariant = $state<"light" | "dark">("dark");
  let previewUrl = $state("");
  let previewError = $state("");
  let settingsKey = $state("");
  let removal = $state<LibraryTheme | null>(null);
  let exportTheme = $state<LibraryTheme | null>(null);
  let newKey = $state("");
  let includeOverrides = $state(false);
  let guideOpen = $state(false);
  let announcement = $state("");
  let editorOpen = $state("");
  const blocked = $derived(dirty || library.busy || store.themesSaving || !library.writable);
  const catalog = $derived<LibraryTheme[]>(
    themes.map((theme) => {
      const installation = library.installations.find((item) => item.key === theme.key);
      return {
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
  const activeTheme = $derived(catalog.find((theme) => theme.key === active) || catalog[0]);
  onMount(() => {
    void library.load();
  });
  $effect(() => {
    const selected = preview;
    const variant = previewVariant;
    let disposed = false;
    let objectUrl = "";
    previewUrl = "";
    previewError = "";
    if (selected)
      void library
        .preview(selected.key, variant)
        .then((url) => {
          objectUrl = url;
          if (disposed) URL.revokeObjectURL(url);
          else previewUrl = url;
        })
        .catch((error) => {
          if (!disposed) previewError = library.message(error);
        });
    return () => {
      disposed = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  });
  async function activate(theme: LibraryTheme) {
    if (blocked) return;
    store.setCurrentTheme(theme.key);
    if (await store.saveThemes()) {
      announcement = at(
        "appearance_demo_active_notice",
        { theme: theme.title },
        "{theme} is now active."
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
  <div class="appearance-settings-footer">
    <span
      >{dirty
        ? at("appearance_unsaved", {}, "Save your changes before managing themes.")
        : at(
            "appearance_library_hint",
            {},
            "Themes are installed without changing the active theme."
          )}</span
    >
    <AdminButton size="sm" disabled={blocked} onclick={library.refresh}
      ><RefreshCw size={14} />{at("btn_refresh", {}, "Refresh")}</AdminButton
    >
    <AdminButton
      size="sm"
      variant="primary"
      disabled={!dirty || library.busy || store.themesSaving}
      onclick={onsave}><Save size={14} />{at("btn_save", {}, "Save")}</AdminButton
    >
  </div>
  {#if library.error}<p class="import-error" role="alert">{library.error}</p>{/if}
  {#if !library.writable}<p class="appearance-settings-note">
      {at(
        "appearance_read_only",
        {},
        "Theme storage is read-only. Check the volume permissions on the server."
      )}
    </p>{/if}
  <header class="library-heading">
    <div>
      <h2>{at("appearance_demo_title", {}, "Make it yours")}</h2>
      <p>
        {at(
          "appearance_demo_subtitle",
          {},
          "Choose a theme, add your own, and shape the look of your shop."
        )}
      </p>
    </div>
    <AdminButton
      disabled={blocked}
      onclick={() => library.exportThemes(catalog.map((theme) => theme.key))}
      >{at("appearance_export_collection", {}, "Download collection")}</AdminButton
    >
    <AdminButton
      onclick={() => {
        guideOpen = true;
      }}
      ><FileText size={15} />{at("appearance_demo_author_guide", {}, "Create a theme")}</AdminButton
    >
  </header>
  <section class="active-theme-summary">
    <span class="active-symbol"><Paintbrush size={21} /></span>
    <div class="active-copy">
      <small>{at("appearance_demo_active_global", {}, "Active theme for all users")}</small><strong
        >{activeTheme?.title || "Default"}<AdminBadge variant="success"
          >{at("appearance_demo_active", {}, "Active")}</AdminBadge
        ></strong
      >
      <p>
        {at(
          "appearance_demo_activate_hint",
          {},
          "Installing a theme adds it to your library. You choose when to activate it."
        )}
      </p>
    </div>
    <AdminButton
      onclick={() => {
        preview = activeTheme || null;
      }}><Eye size={15} />{at("appearance_demo_preview", {}, "Preview")}</AdminButton
    >
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
      {#snippet searchActions()}
        <AdminButton
          variant="primary"
          disabled={blocked}
          onclick={() => {
            openImport();
          }}><Plus size={15} />{at("appearance_demo_add", {}, "Add themes")}</AdminButton
        >
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
                onclick={() => {
                  preview = theme;
                }}
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
                  if (theme.key === "dark") {
                    editorOpen = "default";
                    document
                      .getElementById("appearance-default-editor")
                      ?.scrollIntoView({ behavior: "smooth", block: "start" });
                  } else {
                    settingsKey = theme.key;
                  }
                }}><Settings size={15} /></AdminButton
              >
            </div>
          </div>
        </article>
      {/each}
      {#if !query}<button
          class="theme-add-card"
          disabled={blocked}
          onclick={() => {
            openImport();
          }}
          ><span class="add-symbol"><Plus size={25} /></span><strong
            >{at("appearance_demo_your_theme", {}, "Room for your idea")}</strong
          ><span
            >{at(
              "appearance_demo_your_theme_hint",
              {},
              "Upload a ZIP or connect a repository with a whole collection."
            )}</span
          ><span class="add-card-link"
            >{at("appearance_demo_add", {}, "Add themes")} <Plus size={14} /></span
          ></button
        >{/if}
    </div>
    {#if !filtered.length}<AdminEmptyState
        >{at(
          "appearance_demo_not_found",
          {},
          "No themes found. Try another name."
        )}</AdminEmptyState
      >{/if}
  </section>
  <Accordion.Root type="single" bind:value={editorOpen} class="appearance-editor-accordion">
    <Accordion.Item value="default" class="appearance-editor-item" id="appearance-default-editor"
      ><Accordion.Header
        ><Accordion.Trigger class="appearance-editor-trigger"
          ><span class="editor-symbol"><Settings size={19} /></span><span class="editor-copy"
            ><strong>{at("appearance_demo_default_settings", {}, "Customize Default")}</strong
            ><small
              >{at(
                "appearance_demo_default_settings_hint",
                {},
                "Palette, fonts, corners and logo size"
              )}</small
            ></span
          ><AdminBadge>Default</AdminBadge><ChevronDown size={17} /></Accordion.Trigger
        ></Accordion.Header
      ><Accordion.Content class="appearance-editor-content"
        >{@render defaultEditor()}</Accordion.Content
      ></Accordion.Item
    >
    <Accordion.Item value="behavior" class="appearance-editor-item"
      ><Accordion.Header
        ><Accordion.Trigger class="appearance-editor-trigger"
          ><span class="editor-symbol"><Monitor size={19} /></span><span class="editor-copy"
            ><strong>{at("appearance_demo_behavior", {}, "Display and behavior")}</strong><small
              >{at(
                "appearance_demo_behavior_hint",
                {},
                "User theme mode and compact home screen"
              )}</small
            ></span
          ><ChevronDown size={17} /></Accordion.Trigger
        ></Accordion.Header
      ><Accordion.Content class="appearance-editor-content"
        >{@render behaviorEditor()}</Accordion.Content
      ></Accordion.Item
    >
    <Accordion.Item value="brand" class="appearance-editor-item"
      ><Accordion.Header
        ><Accordion.Trigger class="appearance-editor-trigger"
          ><span class="editor-symbol"><Paintbrush size={19} /></span><span class="editor-copy"
            ><strong>{at("appearance_demo_brand", {}, "Brand and app icon")}</strong><small
              >{at("appearance_demo_brand_hint", {}, "Logo, favicon and brand assets")}</small
            ></span
          ><ChevronDown size={17} /></Accordion.Trigger
        ></Accordion.Header
      ><Accordion.Content class="appearance-editor-content"
        >{@render brandEditor()}</Accordion.Content
      ></Accordion.Item
    >
  </Accordion.Root>
  <div class="appearance-announcement" role="status" aria-live="polite">{announcement}</div>
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
  open={Boolean(preview)}
  title={preview?.title || ""}
  closeLabel={at("close", {}, "Close")}
  onclose={() => {
    preview = null;
  }}
  class="admin-dialog appearance-preview-dialog"
>
  {#if preview}
    <div class="appearance-preview-toolbar">
      <div class="appearance-preview-size">
        <AdminButton
          size="sm"
          variant={previewMobile ? "primary" : "default"}
          aria-pressed={previewMobile}
          onclick={() => {
            previewMobile = true;
          }}><Smartphone size={14} />{at("appearance_demo_mobile", {}, "Mobile")}</AdminButton
        ><AdminButton
          size="sm"
          variant={!previewMobile ? "primary" : "default"}
          aria-pressed={!previewMobile}
          onclick={() => {
            previewMobile = false;
          }}><Monitor size={14} />{at("appearance_demo_desktop", {}, "Desktop")}</AdminButton
        >
      </div>
      <AdminButton
        size="sm"
        disabled={blocked || active === preview.key}
        onclick={() => {
          if (preview) activate(preview);
        }}>{at("appearance_demo_activate", {}, "Activate")}</AdminButton
      >
    </div>
    <div class="appearance-preview-size">
      <AdminButton
        size="sm"
        aria-pressed={previewVariant === "dark"}
        onclick={() => {
          previewVariant = "dark";
        }}>{at("appearance_preview_dark", {}, "Dark")}</AdminButton
      >
      <AdminButton
        size="sm"
        aria-pressed={previewVariant === "light"}
        onclick={() => {
          previewVariant = "light";
        }}>{at("appearance_preview_light", {}, "Light")}</AdminButton
      >
    </div>
    <div class="appearance-live-stage" class:mobile={previewMobile}>
      {#if previewUrl}<iframe
          src={previewUrl}
          title={at("appearance_demo_preview_named", { theme: preview.title }, "Preview {theme}")}
          class="appearance-live-frame"
          sandbox=""
        ></iframe>{:else}<p role="status">{previewError || at("loading", {}, "Loading…")}</p>{/if}
    </div>
  {/if}
</Dialog>
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
    {@render customEditor(settings.key)}
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
      <AdminButton
        disabled={blocked}
        onclick={() => {
          exportTheme = settings;
          settingsKey = "";
          newKey = "";
        }}><Download size={14} />{at("appearance_export", {}, "Export / make a copy")}</AdminButton
      >
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
        if (removal && (await library.mutate(removal.key, "remove"))) removal = null;
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
  title={at("appearance_export", {}, "Export / make a copy")}
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
