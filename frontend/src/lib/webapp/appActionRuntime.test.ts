import { describe, expect, it, vi } from "vitest";

import { createAppActionRuntime, type AppActionRuntimeDeps } from "./appActionRuntime.js";

function createDeps(overrides: Partial<AppActionRuntimeDeps> = {}) {
  const state = {
    adminActiveSection: "stats",
    appSettings: {},
    autoRenewBusy: false,
    canUseInstallGuides: false,
    devicesEnabled: true,
    emailAuthEnabled: true,
    isAdmin: true,
    methods: [{ id: "card" }],
    plans: [{ id: "basic" }],
    publicInstallSubscription: null as Record<string, unknown> | null,
    screen: "home",
    selectedPlan: null as Record<string, unknown> | null,
    selectedTariffPlans: [{ id: "selected" }],
    singleTariffMode: false,
    subscription: { active: true, connect_url: "https://connect.example" },
    supportEnabled: true,
    tariffCatalog: [{ key: "base" }],
    tariffMode: false,
    telegram: null as { openTelegramLink?: (url: string) => void } | null,
    telegramNotificationsStartLink: "https://t.me/example_bot",
    trialActivationResult: null as Record<string, unknown> | null,
    trafficMode: false,
  };
  const billingStore = {
    backToTariffList: vi.fn(),
    closeDeviceTopupModal: vi.fn(),
    closePaymentModal: vi.fn(),
    continueWithSelectedTariff: vi.fn(),
    openDeviceTopupModal: vi.fn(),
    openPaymentModal: vi.fn(),
    openTariffChangeModal: vi.fn(),
    openTopupModal: vi.fn(),
    selectTariff: vi.fn(),
  };
  const installGuidesStore = {
    hydrate: vi.fn((_path: string, payload: Record<string, unknown>) => payload),
    load: vi.fn(),
    loadPublic: vi.fn(async () => ({ subscription: { connect_url: "https://public.example" } })),
    publicPath: vi.fn((shareToken: string) => `/subscription-guides/public/${shareToken}`),
  };
  const calls = {
    markTelegramNotificationsBotOpened: vi.fn(),
    openExternalLink: vi.fn(),
    setActiveTab: vi.fn((tab: string) => {
      void tab;
    }),
    setAdminActiveSection: vi.fn((section: string) => {
      state.adminActiveSection = section;
    }),
    setAutoRenewBusy: vi.fn((busy: boolean) => {
      state.autoRenewBusy = busy;
    }),
    setMode: vi.fn(),
    setPublicInstallSubscription: vi.fn((subscription: Record<string, unknown> | null) => {
      state.publicInstallSubscription = subscription;
    }),
    setPublicInstallToken: vi.fn(),
    setScreen: vi.fn((screen: string) => {
      state.screen = screen;
    }),
    setTelegram: vi.fn((telegram: { openTelegramLink?: (url: string) => void }) => {
      state.telegram = telegram;
    }),
    showToast: vi.fn(),
    syncAppSectionPath: vi.fn(),
  };
  const deps = {
    accountStore: {
      continueTelegramLinkPendingAction: vi.fn(),
      linkTelegramAndActivateTrial: vi.fn(),
      linkTelegramAndClaimReferralWelcome: vi.fn(),
      openLinkEmailDialog: vi.fn(),
      openSetPasswordDialog: vi.fn(),
    },
    actionsStore: {
      activateTrial: vi.fn(),
      applyPromo: vi.fn(),
      clearPromoFieldError: vi.fn(),
      setPromoCode: vi.fn(),
    },
    adminRuntime: {
      cancelAdminAssetsPrefetch: vi.fn(),
      ensureAdminBundle: vi.fn(async () => undefined),
      ensureI18nScope: vi.fn(async () => undefined),
    },
    authStore: {
      finalizeTelegramAuth: vi.fn(),
      openTelegramLogin: vi.fn(),
    },
    billing: {
      postAutoRenew: vi.fn(),
    },
    billingStore,
    canUseInstallGuides: () => state.canUseInstallGuides,
    clearLanguageClickGuard: vi.fn(),
    demoEmail: () => "demo@example.com",
    devicesStore: {
      disconnectDevice: vi.fn(),
      loadDevices: vi.fn(),
    },
    externalLinkActions: {
      openAppLaunchTarget: vi.fn(),
      openAppLink: vi.fn(),
      openExternalLink: calls.openExternalLink,
      refreshAppLaunchTarget: vi.fn(),
    },
    getAdminActiveSection: () => state.adminActiveSection,
    getAppSettings: () => state.appSettings,
    getAutoRenewBusy: () => state.autoRenewBusy,
    getDevicesEnabled: () => state.devicesEnabled,
    getDemoTelegramAuthPayload: () => ({ id: 1 }),
    getEmailAuthEnabled: () => state.emailAuthEnabled,
    getIsAdmin: () => state.isAdmin,
    getIsFileProtocol: () => false,
    getMethods: () => state.methods,
    getOrigin: () => "https://shop.example",
    getPlans: () => state.plans,
    getPreloadHost: () => null,
    getPublicInstallSubscription: () => state.publicInstallSubscription,
    getRoutePathname: () => "/app/admin/stats",
    getScreen: () => state.screen,
    getSelectedPlan: () => state.selectedPlan,
    getSelectedTariffPlans: () => state.selectedTariffPlans,
    getSingleTariffMode: () => state.singleTariffMode,
    getSubscription: () => state.subscription,
    getSupportEnabled: () => state.supportEnabled,
    getTariffCatalog: () => state.tariffCatalog,
    getTariffMode: () => state.tariffMode,
    getTelegram: () => state.telegram,
    getTelegramMiniAppInitData: () => "",
    getTelegramNotificationsStartLink: () => state.telegramNotificationsStartLink,
    getTelegramOAuthClientId: () => 42,
    getTrafficMode: () => state.trafficMode,
    getTrialActivationResult: () => state.trialActivationResult,
    installGuidesStore,
    isDemoAuthLogin: () => false,
    loadData: vi.fn(async () => undefined),
    markTelegramNotificationsBotOpened: calls.markTelegramNotificationsBotOpened,
    refreshTelegram: vi.fn(() => state.telegram),
    routePrefix: "",
    setActiveTab: calls.setActiveTab,
    setAdminActiveSection: calls.setAdminActiveSection,
    setAutoRenewBusy: calls.setAutoRenewBusy,
    setMode: calls.setMode,
    setPublicInstallSubscription: calls.setPublicInstallSubscription,
    setPublicInstallToken: calls.setPublicInstallToken,
    setScreen: calls.setScreen,
    setTelegram: calls.setTelegram,
    showToast: calls.showToast,
    supportStore: {
      loadList: vi.fn(),
      startPolling: vi.fn(),
    },
    syncAppSectionPath: calls.syncAppSectionPath,
    t: (key: string, _params?: Record<string, unknown>, fallback?: string) => fallback || key,
    ...overrides,
  } as AppActionRuntimeDeps;
  return { billingStore, calls, deps, installGuidesStore, state };
}

describe("appActionRuntime", () => {
  it("keeps billing modal inputs live through getters", () => {
    const { billingStore, deps, state } = createDeps();
    const runtime = createAppActionRuntime(deps);

    state.methods = [{ id: "crypto" }];
    state.plans = [{ id: "pro" }];
    state.singleTariffMode = true;
    state.tariffCatalog = [{ key: "premium" }];
    state.tariffMode = true;
    runtime.openPaymentModal();

    expect(billingStore.openPaymentModal).toHaveBeenCalledWith(
      true,
      true,
      state.tariffCatalog,
      state.subscription,
      state.plans,
      "crypto"
    );
  });

  it("switches install actions between guides and connect links", () => {
    const { billingStore, calls, deps, installGuidesStore, state } = createDeps();
    const runtime = createAppActionRuntime(deps);

    state.canUseInstallGuides = true;
    runtime.openInstallOrConnect();

    expect(calls.setScreen).toHaveBeenCalledWith("install");
    expect(installGuidesStore.load).toHaveBeenCalled();
    expect(calls.openExternalLink).not.toHaveBeenCalled();

    state.canUseInstallGuides = false;
    runtime.openInstallOrConnect();

    expect(billingStore.closePaymentModal).toHaveBeenCalled();
    expect(calls.openExternalLink).toHaveBeenCalledWith("https://connect.example");
  });

  it("opens the admin panel through i18n and bundle loading", async () => {
    const { calls, deps } = createDeps();
    const runtime = createAppActionRuntime(deps);

    await runtime.openAdminPanel();

    expect(deps.adminRuntime.cancelAdminAssetsPrefetch).toHaveBeenCalled();
    expect(deps.adminRuntime.ensureI18nScope).toHaveBeenCalledWith("admin");
    expect(deps.adminRuntime.ensureAdminBundle).toHaveBeenCalled();
    expect(calls.syncAppSectionPath).toHaveBeenCalledWith("admin", false, "stats");
  });

  it("opens Telegram notification links through Telegram when available", () => {
    const { calls, deps, state } = createDeps();
    const openTelegramLink = vi.fn();
    state.telegram = { openTelegramLink };
    const runtime = createAppActionRuntime(deps);

    runtime.openTelegramNotificationsBot();

    expect(calls.markTelegramNotificationsBotOpened).toHaveBeenCalled();
    expect(openTelegramLink).toHaveBeenCalledWith("https://t.me/example_bot");
    expect(calls.openExternalLink).not.toHaveBeenCalled();
  });
});
