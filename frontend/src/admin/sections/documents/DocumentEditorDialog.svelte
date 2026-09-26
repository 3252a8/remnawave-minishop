<script lang="ts">
  import { Checkbox, Input } from "$components/ui/index.js";
  import { AdminButton, AdminField, AdminSelect } from "$components/patterns/admin/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { adminRichTextLabels } from "$lib/admin/richTextLabels.js";
  import type {
    AdminDocument,
    AdminDocumentDraft,
  } from "$lib/admin/stores/documentsStore.svelte.js";
  import RichTextEditor from "$lib/richtext/RichTextEditor.svelte";
  import { markdownFormat } from "$lib/richtext/markdownFormat.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    at,
    document = null,
    open,
    saving = false,
    onclose,
    onsave,
  }: {
    at: TranslateFn;
    document?: AdminDocument | null;
    open: boolean;
    saving?: boolean;
    onclose: () => void;
    onsave: (draft: AdminDocumentDraft) => void | Promise<void>;
  } = $props();

  let title = $state("");
  let slug = $state("");
  let markdown = $state("");
  let role = $state("none");
  let showInSettings = $state(false);
  let showInSidebar = $state(false);
  let groupTitle = $state("");
  let sortOrder = $state("0");
  let slugEdited = $state(false);
  let validationError = $state("");
  let loadedDocumentKey = $state("");

  const labels = $derived(
    adminRichTextLabels(at, {
      sourceOn: at("documents_source_on", {}, "Markdown"),
      sourceOff: at("documents_source_off", {}, "Editor"),
    })
  );
  const roleItems = $derived([
    { value: "none", label: at("documents_role_none", {}, "No special role") },
    { value: "privacy_policy", label: at("documents_role_privacy_policy", {}, "Privacy policy") },
    { value: "user_agreement", label: at("documents_role_user_agreement", {}, "User agreement") },
  ]);

  $effect(() => {
    const key = document?.slug || "new";
    if (!open) {
      loadedDocumentKey = "";
      return;
    }
    if (key === loadedDocumentKey) return;
    loadedDocumentKey = key;
    title = document?.title || "";
    slug = document?.slug || "";
    markdown = document?.markdown || "";
    role = document?.role || "none";
    showInSettings = Boolean(document?.show_in_settings);
    showInSidebar = Boolean(document?.show_in_sidebar);
    groupTitle = document?.group_title || "";
    sortOrder = String(document?.sort_order || 0);
    slugEdited = Boolean(document);
    validationError = "";
  });

  function slugify(value: string): string {
    return value
      .trim()
      .toLowerCase()
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9/]+/g, "-")
      .replace(/-+\//g, "/")
      .replace(/\/-+/g, "/")
      .replace(/^[-/]+|[-/]+$/g, "")
      .replace(/\/{2,}/g, "/");
  }

  function titleInput(event: Event): void {
    title = (event.currentTarget as HTMLInputElement).value;
    if (!slugEdited) slug = slugify(title);
  }

  function slugInput(event: Event): void {
    slug = (event.currentTarget as HTMLInputElement).value.toLowerCase();
    slugEdited = true;
  }

  function numberInput(event: Event): void {
    sortOrder = (event.currentTarget as HTMLInputElement).value;
  }

  async function save(): Promise<void> {
    const normalizedTitle = title.trim();
    const normalizedSlug = slug.trim().toLowerCase().replace(/^\/+/, "");
    if (!normalizedTitle || !normalizedSlug) {
      validationError = "documents_required";
      return;
    }
    validationError = "";
    await onsave({
      title: normalizedTitle,
      slug: normalizedSlug,
      markdown,
      role: role === "privacy_policy" || role === "user_agreement" ? role : "none",
      show_in_settings: showInSettings,
      show_in_sidebar: showInSidebar,
      group_title: groupTitle.trim() || null,
      sort_order: Number.isFinite(Number(sortOrder)) ? Math.trunc(Number(sortOrder)) : 0,
    });
  }
</script>

<Dialog
  {open}
  title={document
    ? at("documents_edit_title", {}, "Edit document")
    : at("documents_create_title", {}, "New document")}
  description={at(
    "documents_editor_description",
    {},
    "Documents are published at /:slug. Raw HTML is shown as text."
  )}
  closeLabel={at("close", {}, "Close")}
  focusOnOpen={false}
  onclose={() => {
    if (!saving) onclose();
  }}
  class="admin-dialog admin-document-editor"
>
  <div class="document-editor-stack">
    <div class="document-editor-fields">
      <AdminField label={at("documents_title", {}, "Title")}>
        <Input
          value={title}
          autocomplete="off"
          placeholder={at("documents_title_placeholder", {}, "Privacy policy")}
          oninput={titleInput}
        />
      </AdminField>
      <AdminField
        label={at("documents_slug", {}, "URL slug")}
        hint={at("documents_slug_hint", {}, "The public address is /:slug.")}
      >
        <div class="document-slug-input">
          <span>/</span>
          <Input
            value={slug}
            autocomplete="off"
            placeholder={at("documents_slug_placeholder", {}, "privacy-policy")}
            oninput={slugInput}
          />
        </div>
      </AdminField>
      <AdminField
        label={at("documents_role", {}, "Role")}
        hint={at(
          "documents_role_hint",
          {},
          "Privacy policy and user agreement are used on registration and payment screens."
        )}
      >
        <AdminSelect
          value={role}
          items={roleItems}
          ariaLabel={at("documents_role", {}, "Role")}
          onValueChange={(value) => (role = value)}
        />
      </AdminField>
      <AdminField
        label={at("documents_group", {}, "Group")}
        hint={at("documents_group_hint", {}, "Optional heading for related documents.")}
      >
        <Input
          value={groupTitle}
          autocomplete="off"
          placeholder={at("documents_group_placeholder", {}, "Legal information")}
          oninput={(event) => (groupTitle = (event.currentTarget as HTMLInputElement).value)}
        />
      </AdminField>
      <AdminField
        label={at("documents_order", {}, "Order")}
        hint={at("documents_order_hint", {}, "Lower values are displayed first.")}
      >
        <Input value={sortOrder} type="number" step="1" oninput={numberInput} />
      </AdminField>
    </div>

    <fieldset class="document-editor-visibility">
      <legend>{at("documents_visibility", {}, "Visibility")}</legend>
      <label>
        <Checkbox
          checked={showInSettings}
          ariaLabel={at("documents_show_in_settings", {}, "Show in user settings")}
          onCheckedChange={(checked) => (showInSettings = checked)}
        />
        <span>
          <strong>{at("documents_show_in_settings", {}, "Show in user settings")}</strong>
          <small
            >{at(
              "documents_show_in_settings_hint",
              {},
              "Always display this document there."
            )}</small
          >
        </span>
      </label>
      <label>
        <Checkbox
          checked={showInSidebar}
          ariaLabel={at("documents_show_in_sidebar", {}, "Show in sidebar")}
          onCheckedChange={(checked) => (showInSidebar = checked)}
        />
        <span>
          <strong>{at("documents_show_in_sidebar", {}, "Show in sidebar")}</strong>
          <small
            >{at(
              "documents_show_in_sidebar_hint",
              {},
              "Place it in the public document navigation."
            )}</small
          >
        </span>
      </label>
    </fieldset>

    <AdminField
      label={at("documents_markdown", {}, "Document text")}
      hint={at("documents_markdown_hint", {}, "Format visually or switch to Markdown source.")}
    >
      <div class="document-editor-richtext">
        <RichTextEditor
          value={markdown}
          onInput={(value) => (markdown = value)}
          {labels}
          format={markdownFormat}
          showSource
          documentBlocks
          autofocus
          minHeight="260px"
          placeholder={at("documents_markdown_placeholder", {}, "Document text...")}
        />
      </div>
    </AdminField>

    <div class="admin-dialog-actions">
      {#if validationError}
        <p class="document-editor-error" role="alert">
          {at(validationError, {}, "Enter a title and URL slug")}
        </p>
      {/if}
      <AdminButton disabled={saving} onclick={onclose}>{at("cancel", {}, "Cancel")}</AdminButton>
      <AdminButton variant="primary" disabled={saving} onclick={save}>
        {at(saving ? "documents_saving" : "save", {}, saving ? "Saving…" : "Save")}
      </AdminButton>
    </div>
  </div>
</Dialog>

<style>
  .document-editor-stack {
    display: grid;
    gap: 18px;
  }

  :global(.admin-document-editor) {
    width: min(860px, calc(100vw - 24px));
    max-height: calc(100dvh - 24px);
  }

  :global(.admin-document-editor .dialog-body-scroll) {
    min-height: 0;
  }

  .document-editor-fields {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
  }

  .document-editor-fields :global(.admin-field-label > :last-child) {
    margin-top: auto;
  }

  .document-editor-fields :global(.admin-select-trigger) {
    min-height: 46px;
  }

  .document-slug-input {
    display: flex;
    align-items: center;
    min-width: 0;
    border: 1px solid var(--admin-border, var(--border));
    border-radius: 9px;
    background: var(--admin-surface, var(--panel));
  }

  .document-slug-input > span {
    flex: 0 0 auto;
    padding-left: 11px;
    color: var(--admin-muted, currentColor);
    font-family: var(--font-mono, monospace);
    font-size: 13px;
  }

  .document-slug-input :global(.input) {
    border: 0;
    box-shadow: none;
  }

  .document-editor-visibility {
    display: grid;
    gap: 10px;
    margin: 0;
    padding: 14px;
    border: 1px solid var(--admin-border, var(--border));
    border-radius: 10px;
  }

  .document-editor-visibility legend {
    padding: 0 4px;
    color: var(--admin-muted, currentColor);
    font-size: 12px;
    font-weight: 600;
  }

  .document-editor-visibility label {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    cursor: pointer;
  }

  .document-editor-visibility label > span {
    display: grid;
    gap: 2px;
  }

  .document-editor-visibility small {
    color: var(--admin-muted, currentColor);
    line-height: 1.35;
  }

  .document-editor-richtext :global(.rt-editor) {
    min-height: 260px;
  }

  .document-editor-error {
    flex: 1 1 auto;
    margin: 0;
    color: var(--danger, #dc2626);
  }

  @media (max-width: 640px) {
    .document-editor-fields {
      grid-template-columns: 1fr;
    }
  }
</style>
