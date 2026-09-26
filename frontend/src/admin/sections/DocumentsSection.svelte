<script lang="ts">
  import { ExternalLink, FileText, Pencil, Trash2 } from "$components/ui/icons.js";
  import {
    AdminBadge,
    AdminButton,
    AdminCopyableValue,
    AdminEmptyState,
  } from "$components/patterns/admin/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { getDocumentsStore } from "$lib/admin/context.js";
  import {
    type AdminDocument,
    type AdminDocumentDraft,
  } from "$lib/admin/stores/documentsStore.svelte.js";
  import { withRoutePrefix } from "$lib/webapp/routes.js";
  import { onMount } from "svelte";
  import DocumentEditorDialog from "./documents/DocumentEditorDialog.svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type DocumentGroup = { title: string; documents: AdminDocument[] };

  let {
    at,
    routePrefix = "",
  }: {
    at: TranslateFn;
    routePrefix?: string;
  } = $props();

  const documentsStore = getDocumentsStore();
  const documents = $derived(documentsStore.documents as AdminDocument[]);
  const editorOpen = $derived(Boolean(documentsStore.documentEditorOpen));
  const editingDocument = $derived(documentsStore.editingDocument);
  const loading = $derived(Boolean(documentsStore.documentsLoading));
  const saving = $derived(Boolean(documentsStore.documentsSaving));
  const groupedDocuments = $derived(groupDocuments(documents, at));
  let deleteTarget = $state<AdminDocument | null>(null);

  onMount(() => {
    void documentsStore.loadDocuments();
  });

  function groupDocuments(documents: AdminDocument[], translate: TranslateFn): DocumentGroup[] {
    const groups = new Map<string, AdminDocument[]>();
    for (const document of documents) {
      const title =
        document.group_title || translate("documents_group_ungrouped", {}, "Other documents");
      groups.set(title, [...(groups.get(title) || []), document]);
    }
    return [...groups.entries()].map(([title, grouped]) => ({ title, documents: grouped }));
  }

  function documentUrl(document: AdminDocument): string {
    return withRoutePrefix(
      `/${document.slug
        .split("/")
        .map((segment) => encodeURIComponent(segment))
        .join("/")}`,
      routePrefix
    );
  }

  function roleLabel(document: AdminDocument): string {
    if (document.role === "privacy_policy") {
      return at("documents_role_privacy_policy", {}, "Privacy policy");
    }
    if (document.role === "user_agreement") {
      return at("documents_role_user_agreement", {}, "User agreement");
    }
    return "";
  }

  async function saveDocument(draft: AdminDocumentDraft): Promise<void> {
    const saved = editingDocument
      ? await documentsStore.updateDocument(editingDocument.slug, draft)
      : await documentsStore.createDocument(draft);
    if (saved) {
      documentsStore.closeDocumentEditor();
    }
  }

  async function deleteDocument(): Promise<void> {
    if (!deleteTarget) return;
    if (await documentsStore.deleteDocument(deleteTarget)) deleteTarget = null;
  }
</script>

<section class="documents-section">
  {#if loading}
    <div class="documents-loading" aria-busy="true">
      {#each Array(3) as _}
        <div class="admin-skeleton documents-loading-row"></div>
      {/each}
    </div>
  {:else if !documents.length}
    <AdminEmptyState tone="card" class="documents-empty">
      <FileText size={24} />
      <strong>{at("documents_empty", {}, "No documents yet")}</strong>
      <p>
        {at("documents_empty_hint", {}, "Create a document to publish it at /:slug.")}
      </p>
    </AdminEmptyState>
  {:else}
    <div class="documents-groups">
      {#each groupedDocuments as group (group.title)}
        <section class="documents-group">
          <h3>{group.title}</h3>
          <div class="documents-list">
            {#each group.documents as document (document.slug)}
              {@const url = documentUrl(document)}
              <article class="document-card">
                <div class="document-card-main">
                  <div class="document-card-title">
                    <FileText size={18} aria-hidden="true" />
                    <strong>{document.title}</strong>
                    {#if document.role !== "none"}
                      <AdminBadge variant="muted">{roleLabel(document)}</AdminBadge>
                    {/if}
                  </div>
                  <AdminCopyableValue
                    value={url}
                    text={url}
                    copyLabel={at(
                      "documents_copy_url",
                      { title: document.title },
                      "Copy document URL"
                    )}
                    kind="document-url"
                    oncopy={documentsStore.copyToClipboard}
                    class="document-card-url"
                  />
                  <div class="document-card-meta">
                    {#if document.show_in_settings}
                      <AdminBadge variant="success">
                        {at("documents_visible_in_settings", {}, "In settings")}
                      </AdminBadge>
                    {/if}
                    {#if document.show_in_sidebar}
                      <AdminBadge variant="success">
                        {at("documents_visible_in_sidebar", {}, "In sidebar")}
                      </AdminBadge>
                    {/if}
                    <span
                      >{at(
                        "documents_order_value",
                        { order: document.sort_order },
                        "Order: {order}"
                      )}</span
                    >
                  </div>
                </div>
                <div class="document-card-actions">
                  {#if document.markdown.trim()}
                    <a
                      class="admin-btn admin-btn-sm admin-btn-ghost"
                      href={url}
                      target="_blank"
                      rel="noreferrer noopener"
                      title={at("documents_open", { title: document.title }, "Open document")}
                    >
                      <ExternalLink size={14} />
                      <span>{at("open", {}, "Open")}</span>
                    </a>
                  {:else}
                    <AdminButton size="sm" variant="ghost" disabled>
                      <ExternalLink size={14} />
                      <span>{at("open", {}, "Open")}</span>
                    </AdminButton>
                  {/if}
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={() => documentsStore.openEditDocument(document)}
                  >
                    <Pencil size={14} />
                    <span>{at("documents_edit_title", {}, "Edit")}</span>
                  </AdminButton>
                  <AdminButton
                    size="sm"
                    variant="dangerSoft"
                    title={at("delete", {}, "Delete")}
                    aria-label={at("delete", {}, "Delete")}
                    onclick={() => (deleteTarget = document)}
                  >
                    <Trash2 size={14} />
                  </AdminButton>
                </div>
              </article>
            {/each}
          </div>
        </section>
      {/each}
    </div>
  {/if}
</section>

<DocumentEditorDialog
  {at}
  document={editingDocument}
  open={editorOpen}
  {saving}
  onclose={() => {
    documentsStore.closeDocumentEditor();
  }}
  onsave={saveDocument}
/>

<Dialog
  open={Boolean(deleteTarget)}
  title={at("documents_delete_title", {}, "Delete document?")}
  description={deleteTarget
    ? at(
        "documents_delete_description",
        { title: deleteTarget.title },
        "{title} will no longer be available at its public URL."
      )
    : ""}
  closeLabel={at("close", {}, "Close")}
  onclose={() => {
    if (!saving) deleteTarget = null;
  }}
  class="admin-dialog admin-document-delete-dialog"
>
  <div class="admin-dialog-actions">
    <AdminButton disabled={saving} onclick={() => (deleteTarget = null)}>
      {at("cancel", {}, "Cancel")}
    </AdminButton>
    <AdminButton variant="danger" disabled={saving} onclick={deleteDocument}>
      <Trash2 size={14} />
      {at(saving ? "documents_deleting" : "delete", {}, saving ? "Deleting…" : "Delete")}
    </AdminButton>
  </div>
</Dialog>

<style>
  .documents-section,
  .documents-groups,
  .documents-list {
    display: grid;
    gap: 16px;
  }

  .document-card-meta {
    color: var(--admin-muted, currentColor);
  }

  .documents-loading {
    display: grid;
    gap: 10px;
  }

  .documents-loading-row {
    height: 94px;
    border-radius: 10px;
  }

  :global(.documents-empty) {
    min-height: 240px;
  }

  .documents-group {
    display: grid;
    gap: 8px;
  }

  .documents-group h3 {
    margin: 0;
    color: var(--admin-muted, currentColor);
    font-size: 12px;
    font-weight: 650;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .document-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
    padding: 15px;
    border: 1px solid var(--admin-border, var(--border));
    border-radius: 10px;
    background: var(--admin-surface, var(--panel));
  }

  .document-card-main {
    display: grid;
    min-width: 0;
    gap: 7px;
  }

  .document-card-title,
  .document-card-meta,
  .document-card-actions {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .document-card-title {
    min-width: 0;
  }

  .document-card-title strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  :global(.document-card-url) {
    width: fit-content;
    max-width: 100%;
    color: var(--admin-muted, currentColor);
    font-family: var(--font-mono, monospace);
    font-size: 12px;
  }

  .document-card-meta {
    flex-wrap: wrap;
    font-size: 12px;
  }

  .document-card-actions {
    flex: 0 0 auto;
  }

  @media (max-width: 720px) {
    .document-card {
      align-items: stretch;
      flex-direction: column;
    }

    .document-card-actions {
      flex-wrap: wrap;
    }
  }
</style>
