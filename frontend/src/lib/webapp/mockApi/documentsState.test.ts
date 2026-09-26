import { afterEach, describe, expect, it, vi } from "vitest";
import { loadDemoDocuments, storeDemoDocuments } from "./documentsState";

afterEach(() => vi.unstubAllGlobals());

describe("demo document navigation persistence", () => {
  it("restores nested documents after navigation and retains updates and deletion", () => {
    const storage = new Map<string, string>();
    vi.stubGlobal("window", {
      sessionStorage: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => storage.set(key, value),
      },
    });
    const slug = "guides/install/linux";
    const document = { slug, title: "Linux", markdown: "# Guide", show_in_sidebar: true };
    storeDemoDocuments(new Map([[slug, document]]));
    const restored = loadDemoDocuments();
    expect(restored.get(slug)).toEqual(document);
    restored.set(slug, { ...document, markdown: "Updated" });
    storeDemoDocuments(restored);
    expect(loadDemoDocuments().get(slug)?.markdown).toBe("Updated");
    restored.delete(slug);
    storeDemoDocuments(restored);
    expect(loadDemoDocuments().size).toBe(0);
  });

  it.each([
    "{",
    "null",
    '{"slug":"guide"}',
    '[null, {}, {"slug":"guide","title":3,"markdown":"text"}]',
  ])("ignores malformed stored data %s", (raw) => {
    vi.stubGlobal("window", { sessionStorage: { getItem: () => raw } });
    expect(loadDemoDocuments().size).toBe(0);
  });

  it("keeps storage failures from breaking the demo", () => {
    vi.stubGlobal("window", {
      sessionStorage: {
        getItem: () => {
          throw new Error("blocked");
        },
        setItem: () => {
          throw new Error("blocked");
        },
      },
    });
    expect(loadDemoDocuments().size).toBe(0);
    expect(() => storeDemoDocuments(new Map())).not.toThrow();
  });
});
