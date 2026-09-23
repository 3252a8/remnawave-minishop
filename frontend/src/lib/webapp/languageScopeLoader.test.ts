import { describe, expect, it, vi } from "vitest";

import { createLanguageScopeLoader } from "./languageScopeLoader.js";

describe("createLanguageScopeLoader", () => {
  it("loads only the requested language and scope, then reuses them", async () => {
    const fetchScope = vi.fn(async (scope: string, language: string) => ({
      ok: true,
      i18n: { [language]: { [`${scope}_label`]: language } },
    }));
    const mergeMessages = vi.fn();
    const loader = createLanguageScopeLoader({
      initialLanguages: ["ru"],
      normalizeLanguage: (language) => language,
      fetchScope,
      mergeMessages,
    });

    await loader.load("webapp", "ru");
    await loader.load("webapp", "en");
    await loader.load("webapp", "en");
    await loader.load("admin", "en");
    await loader.load("admin", "en", true);

    expect(fetchScope.mock.calls).toEqual([
      ["webapp", "en"],
      ["admin", "en"],
      ["admin", "en"],
    ]);
    expect(mergeMessages).toHaveBeenCalledWith({ en: { webapp_label: "en" } });
    expect(mergeMessages).toHaveBeenCalledWith({ en: { admin_label: "en" } });
  });

  it("shares a concurrent request and retries after failure", async () => {
    let resolve!: (value: { ok: boolean; i18n: { en: { title: string } } }) => void;
    const pending = new Promise<{ ok: boolean; i18n: { en: { title: string } } }>((done) => {
      resolve = done;
    });
    const fetchScope = vi
      .fn()
      .mockReturnValueOnce(pending)
      .mockRejectedValueOnce(new Error("offline"));
    const loader = createLanguageScopeLoader({
      initialLanguages: [],
      normalizeLanguage: (language) => language,
      fetchScope,
      mergeMessages: vi.fn(),
    });

    const first = loader.load("webapp", "en");
    const duplicate = loader.load("webapp", "en");
    expect(first).toBe(duplicate);
    expect(fetchScope).toHaveBeenCalledTimes(1);
    resolve({ ok: true, i18n: { en: { title: "Title" } } });
    await first;
    await expect(loader.load("admin", "en")).rejects.toThrow("offline");
    expect(fetchScope).toHaveBeenCalledTimes(2);
  });
});
