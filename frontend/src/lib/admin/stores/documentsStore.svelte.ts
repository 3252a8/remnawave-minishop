import { copyTextToClipboard } from "../../webapp/clipboard.js";
import { adminErrorMessage } from "../errors.js";
import {
  buildAdminDocumentPath,
  buildAdminDocumentsPath,
  unwrap,
  type ApiClient,
  type PostPayload,
} from "../../webapp/publicApi.js";
import type { components } from "../../api/openapi.generated.js";
import { defineRawStateProperty } from "./rawStateProperty.js";

type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type AdminDocumentsApi = ApiClient["api"];

export type AdminDocumentRole = components["schemas"]["AdminDocumentOut"]["role"];
export type AdminDocumentDraft = components["schemas"]["AdminDocumentCreateBody"];
export type AdminDocument = components["schemas"]["AdminDocumentOut"];

type DocumentsState = {
  documentEditorOpen: boolean;
  editingDocument: AdminDocument | null;
  documents: AdminDocument[];
  documentsLoading: boolean;
  documentsSaving: boolean;
};
type DocumentsStoreOptions = {
  api: AdminDocumentsApi;
  at: TranslateFn;
  onToast: ToastFn;
};
export type DocumentsStore = DocumentsState & {
  closeDocumentEditor: () => void;
  loadDocuments: () => Promise<void>;
  openCreateDocument: () => void;
  openEditDocument: (document: AdminDocument) => void;
  createDocument: (draft: AdminDocumentDraft) => Promise<AdminDocument | null>;
  updateDocument: (
    previousSlug: string,
    draft: AdminDocumentDraft
  ) => Promise<AdminDocument | null>;
  deleteDocument: (document: AdminDocument) => Promise<boolean>;
  copyToClipboard: (value: string) => Promise<void>;
};

function sortedDocuments(source: AdminDocument[]): AdminDocument[] {
  return [...source].sort(
    (left, right) =>
      (left.group_title || "").localeCompare(right.group_title || "") ||
      left.sort_order - right.sort_order ||
      left.title.localeCompare(right.title)
  );
}

export function defaultAdminDocumentDraft(): AdminDocumentDraft {
  return {
    title: "",
    slug: "",
    markdown: "",
    role: "none",
    show_in_settings: false,
    show_in_sidebar: false,
    group_title: null,
    sort_order: 0,
  };
}

export function createDocumentsStore({ api, at, onToast }: DocumentsStoreOptions): DocumentsStore {
  let documents = $state.raw<AdminDocument[]>([]);
  const state = $state<Omit<DocumentsState, "documents">>({
    documentEditorOpen: false,
    editingDocument: null,
    documentsLoading: false,
    documentsSaving: false,
  });
  const store = Object.create(state) as DocumentsStore;
  defineRawStateProperty(store, "documents", {
    get: () => documents,
    set: (value) => {
      documents = value;
    },
  });

  async function loadDocuments(): Promise<void> {
    state.documentsLoading = true;
    try {
      documents = sortedDocuments(unwrap(await api(buildAdminDocumentsPath())).documents);
    } catch (failure) {
      onToast(
        adminErrorMessage(failure, at, at("documents_load_failed", {}, "Could not load documents"))
      );
    } finally {
      state.documentsLoading = false;
    }
  }

  function openCreateDocument(): void {
    state.editingDocument = null;
    state.documentEditorOpen = true;
  }

  function openEditDocument(document: AdminDocument): void {
    state.editingDocument = document;
    state.documentEditorOpen = true;
  }

  function closeDocumentEditor(): void {
    state.documentEditorOpen = false;
    state.editingDocument = null;
  }

  function storeDocument(document: AdminDocument, previousSlug = document.slug): void {
    documents = sortedDocuments([
      ...documents.filter((item) => item.slug !== previousSlug && item.slug !== document.slug),
      document,
    ]);
  }

  async function createDocument(draft: AdminDocumentDraft): Promise<AdminDocument | null> {
    state.documentsSaving = true;
    try {
      const payload = draft satisfies PostPayload<"/api/admin/documents">;
      const document = unwrap(
        await api<"/admin/documents", { method: "POST"; body: string }>(buildAdminDocumentsPath(), {
          method: "POST",
          body: JSON.stringify(payload),
        })
      );
      storeDocument(document);
      onToast(at("documents_created", {}, "Document created"));
      return document;
    } catch (failure) {
      onToast(
        adminErrorMessage(failure, at, at("documents_save_failed", {}, "Could not save document"))
      );
      return null;
    } finally {
      state.documentsSaving = false;
    }
  }

  async function updateDocument(
    previousSlug: string,
    draft: AdminDocumentDraft
  ): Promise<AdminDocument | null> {
    state.documentsSaving = true;
    try {
      const payload = draft satisfies components["schemas"]["AdminDocumentUpdateBody"];
      const document = unwrap(
        await api<ReturnType<typeof buildAdminDocumentPath>, { method: "PUT"; body: string }>(
          buildAdminDocumentPath(previousSlug),
          { method: "PUT", body: JSON.stringify(payload) }
        )
      );
      storeDocument(document, previousSlug);
      onToast(at("documents_saved", {}, "Document saved"));
      return document;
    } catch (failure) {
      onToast(
        adminErrorMessage(failure, at, at("documents_save_failed", {}, "Could not save document"))
      );
      return null;
    } finally {
      state.documentsSaving = false;
    }
  }

  async function deleteDocument(document: AdminDocument): Promise<boolean> {
    state.documentsSaving = true;
    try {
      unwrap(await api(buildAdminDocumentPath(document.slug), { method: "DELETE" }));
      documents = documents.filter((item) => item.slug !== document.slug);
      onToast(at("documents_deleted", {}, "Document deleted"));
      return true;
    } catch (failure) {
      onToast(
        adminErrorMessage(
          failure,
          at,
          at("documents_delete_failed", {}, "Could not delete document")
        )
      );
      return false;
    } finally {
      state.documentsSaving = false;
    }
  }

  async function copyToClipboard(value: string): Promise<void> {
    if (await copyTextToClipboard(value)) {
      onToast(at("documents_url_copied", {}, "Document URL copied"));
    } else {
      onToast(at("documents_url_copy_failed", {}, "Could not copy document URL"));
    }
  }

  return Object.assign(store, {
    closeDocumentEditor,
    loadDocuments,
    openCreateDocument,
    openEditDocument,
    createDocument,
    updateDocument,
    deleteDocument,
    copyToClipboard,
  });
}
