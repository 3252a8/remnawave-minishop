import { describe, expect, it, vi } from "vitest";

import { createDocumentsStore, defaultAdminDocumentDraft } from "./documentsStore.svelte.js";

const at = (_key: string, _params?: Record<string, unknown>, fallback?: string): string =>
  fallback || "";

describe("documentsStore", () => {
  it("loads documents in their group and display order", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      documents: [
        {
          title: "Terms",
          slug: "terms",
          markdown: "# Terms",
          role: "user_agreement",
          show_in_settings: true,
          show_in_sidebar: true,
          group_title: "Legal",
          sort_order: 20,
        },
        {
          title: "About",
          slug: "about",
          markdown: "# About",
          role: "none",
          show_in_settings: false,
          show_in_sidebar: false,
          group_title: "",
          sort_order: 0,
        },
      ],
    });
    const store = createDocumentsStore({ api, at, onToast: vi.fn() });

    await store.loadDocuments();

    expect(api).toHaveBeenCalledWith("/admin/documents");
    expect(store.documents.map((document) => document.slug)).toEqual(["about", "terms"]);
    expect(store.documents[0].role).toBe("none");
    expect(store.documents[0].group_title).toBe("");

    store.openEditDocument(store.documents[0]);
    expect(store.documentEditorOpen).toBe(true);
    expect(store.editingDocument?.slug).toBe("about");

    store.openCreateDocument();
    expect(store.editingDocument).toBeNull();

    store.closeDocumentEditor();
    expect(store.documentEditorOpen).toBe(false);
  });

  it("replaces the prior slug after an edited document is saved", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        documents: [
          {
            title: "Policy",
            slug: "policy",
            markdown: "# Policy",
            role: "privacy_policy",
            show_in_settings: true,
            show_in_sidebar: false,
            group_title: "Legal",
            sort_order: 0,
          },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        title: "Privacy policy",
        slug: "privacy-policy",
        markdown: "# Privacy",
        role: "privacy_policy",
        show_in_settings: true,
        show_in_sidebar: true,
        group_title: "Legal",
        sort_order: 1,
      });
    const onToast = vi.fn();
    const store = createDocumentsStore({ api, at, onToast });
    await store.loadDocuments();

    const draft = {
      ...defaultAdminDocumentDraft(),
      title: "Privacy policy",
      slug: "privacy-policy",
      markdown: "# Privacy",
      role: "privacy_policy" as const,
      show_in_settings: true,
      show_in_sidebar: true,
      group_title: "Legal",
      sort_order: 1,
    };
    await store.updateDocument("policy", draft);

    expect(api).toHaveBeenLastCalledWith("/admin/documents/policy", {
      method: "PUT",
      body: JSON.stringify(draft),
    });
    expect(store.documents).toHaveLength(1);
    expect(store.documents[0]).toMatchObject({ slug: "privacy-policy", show_in_sidebar: true });
    expect(onToast).toHaveBeenLastCalledWith("Document saved");
  });
});
