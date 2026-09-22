import { describe, expect, it, vi } from "vitest";

import { createAdminRuntime } from "./adminRuntime.js";
type TestOverrides = { [key: string]: Record<string, unknown> | undefined };

function makeRuntime(overrides: TestOverrides = {}) {
  const state = {
    bundleApi: null,
    bundleError: "",
    isMock: false,
    shouldPrefetch: true,
    ...overrides.state,
  };
  const deps = {
    fetchI18nScope: vi.fn(async (scope) => ({
      i18n: { [scope]: { ok: true } },
      ok: true,
    })),
    getAdminAssets: vi.fn(() => ({})),
    getIsMock: () => state.isMock,
    getShouldPrefetch: () => state.shouldPrefetch,
    invalidateTariffOptionCaches: vi.fn(),
    loadData: vi.fn(async () => null),
    mergeMessages: vi.fn(),
    resetInstallGuides: vi.fn(),
    setBundleState: vi.fn((api, error) => {
      state.bundleApi = api;
      state.bundleError = error;
    }),
    ...overrides.deps,
  };
  return { deps, runtime: createAdminRuntime(deps), state };
}

describe("createAdminRuntime", () => {
  it("loads admin i18n once and caches the scope", async () => {
    const { deps, runtime } = makeRuntime();

    await runtime.ensureI18nScope("admin");
    await runtime.ensureI18nScope("admin");

    expect(deps.fetchI18nScope).toHaveBeenCalledTimes(1);
    expect(deps.fetchI18nScope).toHaveBeenCalledWith("admin");
    expect(deps.mergeMessages).toHaveBeenCalledWith({ admin: { ok: true } });
  });

  it("loads admin translations on direct entry and refreshes them after a plugin update", async () => {
    const bundle = {
      mount: vi.fn(() => ({ destroy: vi.fn() })),
      registerRuntimeExtensions: vi.fn(),
    };
    (globalThis as Record<string, unknown>).window = { SubscriptionWebAppAdmin: bundle };
    const loadRuntimeExtensions = vi.fn().mockResolvedValueOnce(1).mockResolvedValueOnce(2);
    const { deps, runtime } = makeRuntime({ deps: { loadRuntimeExtensions } });
    try {
      await runtime.ensureAdminBundle();
      await runtime.ensureAdminBundle();
      expect(deps.fetchI18nScope).toHaveBeenCalledTimes(2);
      expect(deps.fetchI18nScope).toHaveBeenNthCalledWith(1, "admin");
      expect(deps.fetchI18nScope).toHaveBeenNthCalledWith(2, "admin");
      expect(loadRuntimeExtensions).toHaveBeenCalledTimes(2);
    } finally {
      delete (globalThis as Record<string, unknown>).window;
    }
  });

  it("refreshes translations before running the persisted-save flow", async () => {
    const { deps, runtime } = makeRuntime();

    await runtime.handleAdminTranslationsSaved();

    expect(deps.fetchI18nScope).toHaveBeenCalledWith("webapp");
    expect(deps.fetchI18nScope).toHaveBeenCalledWith("admin");
    expect(deps.invalidateTariffOptionCaches).toHaveBeenCalledOnce();
    expect(deps.resetInstallGuides).toHaveBeenCalledOnce();
    expect(deps.loadData).toHaveBeenCalledWith({ fresh: true, preserveView: true });
  });

  it("refreshes relevant frontend settings without reloading or leaving admin", async () => {
    const { deps, runtime } = makeRuntime();

    await runtime.handleAdminPersistedSaved({
      updates: { WEBAPP_LOGO_URL: "https://example.test/logo.png" },
    });

    expect(deps.loadData).toHaveBeenCalledWith({ fresh: true, preserveView: true });
  });

  it("refreshes live app data without reloading for the partner feature flag", async () => {
    const { deps, runtime } = makeRuntime();

    await runtime.handleAdminPersistedSaved({
      updates: { PARTNER_PROGRAM_ENABLED: true },
    });

    expect(deps.loadData).toHaveBeenCalledWith({ fresh: true, preserveView: true });
  });

  it("keeps save success when the refresh load fails", async () => {
    const { deps, runtime } = makeRuntime({
      deps: {
        loadData: vi.fn(async () => {
          throw new Error("refresh failed");
        }),
      },
    });

    await runtime.handleAdminPersistedSaved();

    expect(deps.invalidateTariffOptionCaches).toHaveBeenCalledOnce();
    expect(deps.resetInstallGuides).toHaveBeenCalledOnce();
  });

  it("mounts and destroys admin bundle through the runtime", () => {
    const { runtime } = makeRuntime();
    const destroyed = vi.fn();
    const updated = vi.fn();
    const target = { replaceChildren: vi.fn() } as unknown as HTMLElement;
    const api = {
      mount: vi.fn(() => ({ destroy: destroyed, update: updated })),
    };
    const runtimeWithApi = createAdminRuntime({
      ...makeRuntime().deps,
      setBundleState: vi.fn(),
    });

    // Injecting the loaded bundle through the global mirrors adminBundle's normal read path.
    (globalThis as Record<string, unknown>).window = {
      SubscriptionWebAppAdmin: api,
    };

    return runtimeWithApi.ensureAdminBundle().then(() => {
      runtimeWithApi.syncAdminMount({
        props: { initialSection: "stats" },
        shouldMount: true,
        target,
      });
      runtimeWithApi.syncAdminMount({
        props: { initialSection: "users" },
        shouldMount: true,
        target,
      });
      runtimeWithApi.syncAdminMount({
        props: {},
        shouldMount: false,
        target: null,
      });

      expect(api.mount).toHaveBeenCalledOnce();
      expect(updated).toHaveBeenCalledWith({ initialSection: "users" });
      expect(destroyed).toHaveBeenCalledOnce();
      delete (globalThis as Record<string, unknown>).window;
      expect(runtime).toBeTruthy();
    });
  });
});
