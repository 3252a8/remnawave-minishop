import { describe, expect, it, vi } from "vitest";

import { createAppLoadExecutor } from "./appLoadExecutor.js";
import { resetShellState, shellState } from "./shellState.svelte";
type TestOverrides = { [key: string]: Record<string, unknown> | undefined };

function createPayload(overrides: TestOverrides = {}) {
  return {
    ok: true,
    payment_methods: [{ id: "card" }],
    plans: [{ months: 1, price: 100 }],
    settings: {
      my_devices_enabled: true,
      subscription_guides_enabled: true,
      support_tickets_enabled: true,
    },
    subscription: { active: true },
    support_unread_count: 3,
    user: { is_admin: false },
    ...overrides,
  };
}

function createDeps(overrides: TestOverrides = {}) {
  const state = {
    activeTab: "home",
    adminActiveSection: "stats",
    modal: {
      changeModalOpen: false,
      deviceTopupModalOpen: false,
      topupKind: "regular",
      topupModalOpen: false,
    },
    mode: "",
    pathname: "/",
    screen: "home",
    search: "",
    windowSearch: "",
    ...overrides.state,
  };
  resetShellState({
    activeTab: state.activeTab,
    adminActiveSection: state.adminActiveSection,
    mode: state.mode || "loading",
    screen: state.screen,
  });
  const adminRuntime = {
    cancelAdminAssetsPrefetch: vi.fn(),
    ensureAdminBundle: vi.fn(() => Promise.resolve({})),
    ensureI18nScope: vi.fn(() => Promise.resolve({})),
    preloadAdminBundle: vi.fn(() => Promise.resolve({})),
    scheduleAdminAssetsPrefetch: vi.fn(),
  };
  type FakeBillingState = {
    paymentStep: string;
    renewHwidDevices: boolean;
    selectedMethod: string;
    selectedPlan: { months: number } | null;
    selectedTariffKey: string;
  };
  let billingState: FakeBillingState = {
    paymentStep: "method",
    renewHwidDevices: false,
    selectedMethod: "old",
    selectedPlan: { months: 12 },
    selectedTariffKey: "premium",
  };
  const billingStore = {
    loadDeviceTopupOptions: vi.fn(() => Promise.resolve()),
    loadTariffChangeOptions: vi.fn(() => Promise.resolve()),
    loadTopupOptions: vi.fn(() => Promise.resolve()),
    update: vi.fn((updater: (s: FakeBillingState) => FakeBillingState) => {
      billingState = updater(billingState);
    }),
  };
  const deps = {
    adminRuntime,
    applyPostLoadBillingDeeplinks: vi.fn(),
    currentSearchParams: () => new URLSearchParams(state.search),
    dataClientLoadData: vi.fn(() => Promise.resolve(createPayload())),
    ensureWebappLanguage: vi.fn(() => Promise.resolve()),
    getModalState: () => state.modal,
    getWindowSearch: () => state.windowSearch,
    hydrateSupportUnread: vi.fn(),
    initialAdminSectionFromLocation: vi.fn(() => "stats"),
    isDocsDemo: vi.fn(() => false),
    isMock: vi.fn(() => false),
    loadDeviceTopupOptions: billingStore.loadDeviceTopupOptions,
    loadInstallGuides: vi.fn(() => Promise.resolve("install-guides")),
    loadSectionData: vi.fn(() => Promise.resolve()),
    loadTariffChangeOptions: billingStore.loadTariffChangeOptions,
    loadTopupOptions: billingStore.loadTopupOptions,
    rememberLanguage: vi.fn(),
    resetBillingSelection: vi.fn((defaultMethod) => {
      billingStore.update((billing) => ({
        ...billing,
        paymentStep: "tariff",
        renewHwidDevices: true,
        selectedMethod: defaultMethod,
        selectedPlan: null,
        selectedTariffKey: "",
      }));
    }),
    routePathnameFromLocation: () => state.pathname,
    routePrefix: "",
    showAdminUnavailable: vi.fn(),
    syncLoadedRoute: vi.fn(),
    ...overrides.deps,
  };
  return {
    adminRuntime,
    billingStore,
    billingState: () => billingState,
    deps,
    executor: createAppLoadExecutor(deps as unknown as Parameters<typeof createAppLoadExecutor>[0]),
    state,
  };
}

describe("createAppLoadExecutor", () => {
  it("loads app data and applies route, billing, support, and section effects", async () => {
    const payload = createPayload();
    const { billingState, deps, executor } = createDeps({
      deps: {
        dataClientLoadData: vi.fn(() => Promise.resolve(payload)),
      },
      state: { pathname: "/support/42", windowSearch: "?topup=regular" },
    });

    await expect(executor.loadData({ fresh: true })).resolves.toBe(payload);

    expect(deps.dataClientLoadData).toHaveBeenCalledWith({ fresh: true });
    expect(shellState.data).toBe(payload);
    expect(billingState()).toMatchObject({
      paymentStep: "tariff",
      renewHwidDevices: true,
      selectedMethod: "card",
      selectedPlan: null,
      selectedTariffKey: "",
    });
    expect(shellState).toMatchObject({ activeTab: "support", mode: "app", screen: "support" });
    expect(deps.hydrateSupportUnread).toHaveBeenCalledWith({
      supportEnabled: true,
      unreadCount: 3,
    });
    expect(deps.syncLoadedRoute).toHaveBeenCalledWith({
      initialAdminSection: null,
      initialSupportTicketId: 42,
      section: "support",
      supportTargetPath: "/support/42",
    });
    expect(deps.loadSectionData).toHaveBeenCalledWith(
      expect.objectContaining({
        initialSupportTicketId: 42,
        payload,
        section: "support",
      })
    );
    expect(deps.applyPostLoadBillingDeeplinks).toHaveBeenCalledWith({
      defaultMethod: "card",
      plans: payload.plans,
      search: "?topup=regular",
      subscription: payload.subscription,
    });
  });

  it("keeps a section selected while the initial data request is in flight", async () => {
    let resolvePayload!: (payload: ReturnType<typeof createPayload>) => void;
    const pendingPayload = new Promise<ReturnType<typeof createPayload>>((resolve) => {
      resolvePayload = resolve;
    });
    const { deps, executor, state } = createDeps({
      deps: {
        dataClientLoadData: vi.fn(() => pendingPayload),
      },
    });

    const loading = executor.loadData();
    expect(deps.dataClientLoadData).toHaveBeenCalledOnce();

    state.pathname = "/settings";
    shellState.activeTab = "settings";
    shellState.screen = "settings";
    resolvePayload(createPayload());

    await loading;

    expect(shellState).toMatchObject({ activeTab: "settings", mode: "app", screen: "settings" });
    expect(deps.syncLoadedRoute).toHaveBeenCalledWith(
      expect.objectContaining({ section: "settings" })
    );
  });

  it("loads the admin bundle for admin routes", async () => {
    const payload = createPayload({ user: { is_admin: true } });
    const { adminRuntime, deps, executor } = createDeps({
      deps: {
        dataClientLoadData: vi.fn(() => Promise.resolve(payload)),
      },
      state: { pathname: "/admin/users" },
    });

    await executor.loadData();

    expect(adminRuntime.cancelAdminAssetsPrefetch).toHaveBeenCalledOnce();
    expect(adminRuntime.preloadAdminBundle).toHaveBeenCalledOnce();
    expect(adminRuntime.ensureI18nScope).toHaveBeenCalledWith("admin");
    expect(adminRuntime.ensureAdminBundle).toHaveBeenCalledOnce();
    expect(shellState).toMatchObject({
      activeTab: "settings",
      adminActiveSection: "stats",
      mode: "app",
      screen: "admin",
    });
    expect(deps.syncLoadedRoute).toHaveBeenCalledWith(
      expect.objectContaining({
        initialAdminSection: "stats",
        section: "admin",
      })
    );
  });

  it("starts admin resources before the initial data response", async () => {
    let resolvePayload!: (payload: ReturnType<typeof createPayload>) => void;
    const pendingPayload = new Promise<ReturnType<typeof createPayload>>((resolve) => {
      resolvePayload = resolve;
    });
    const { adminRuntime, deps, executor } = createDeps({
      deps: { dataClientLoadData: vi.fn(() => pendingPayload) },
      state: { pathname: "/admin/plugins" },
    });

    const loading = executor.loadData();
    expect(deps.dataClientLoadData).toHaveBeenCalledOnce();
    expect(adminRuntime.preloadAdminBundle).toHaveBeenCalledOnce();
    expect(adminRuntime.ensureI18nScope).not.toHaveBeenCalled();
    expect(adminRuntime.ensureAdminBundle).not.toHaveBeenCalled();

    resolvePayload(createPayload({ user: { is_admin: true } }));
    await loading;
    expect(adminRuntime.ensureI18nScope).toHaveBeenCalledWith("admin");
    expect(adminRuntime.ensureAdminBundle).toHaveBeenCalledOnce();
    expect(shellState.screen).toBe("admin");
  });

  it("falls back to settings when admin bundle loading fails", async () => {
    const payload = createPayload({ user: { is_admin: true } });
    const { adminRuntime, deps, executor } = createDeps({
      deps: {
        dataClientLoadData: vi.fn(() => Promise.resolve(payload)),
      },
      state: { pathname: "/admin/payments" },
    });
    adminRuntime.ensureAdminBundle.mockRejectedValueOnce(new Error("missing bundle"));

    await executor.loadData();

    expect(shellState).toMatchObject({
      activeTab: "settings",
      mode: "app",
      screen: "settings",
    });
    expect(deps.showAdminUnavailable).toHaveBeenCalledOnce();
    expect(deps.syncLoadedRoute).toHaveBeenCalledWith(
      expect.objectContaining({
        section: "settings",
      })
    );
  });

  it("refreshes open billing modal option lists after load", async () => {
    const { billingStore, executor } = createDeps({
      state: {
        modal: {
          changeModalOpen: true,
          deviceTopupModalOpen: true,
          topupKind: "premium",
          topupModalOpen: true,
        },
      },
    });

    await executor.loadData();

    expect(billingStore.loadTopupOptions).toHaveBeenCalledWith("premium");
    expect(billingStore.loadDeviceTopupOptions).toHaveBeenCalledOnce();
    expect(billingStore.loadTariffChangeOptions).toHaveBeenCalledOnce();
  });
});
