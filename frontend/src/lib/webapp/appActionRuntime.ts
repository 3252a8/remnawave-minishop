import { createAccountUiActions } from "./accountUiActions.js";
import { createAdminPanelActions } from "./adminPanelActions.js";
import { createAutoRenewAction } from "./autoRenewAction.js";
import { createBillingModalActions } from "./billingModalActions.js";
import { createClipboardActions } from "./clipboardActions.js";
import { createConnectActions } from "./connectActions.js";
import { createInstallRuntime } from "./installRuntime.js";
import { createPrimaryPayActionLabel } from "./primaryPayActionLabel.js";
import { createPromoTrialActions } from "./promoTrialActions.js";
import { createTariffActions } from "./tariffActions.js";
import { createTelegramLoginActions } from "./telegramLoginActions.js";
import { createWebappNavigation } from "./webappNavigation.js";
import { shellState } from "./shellState.svelte";

type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

type AccountUiDeps = Parameters<typeof createAccountUiActions>[0];
type AdminPanelDeps = Parameters<typeof createAdminPanelActions>[0];
type AutoRenewDeps = Parameters<typeof createAutoRenewAction>[0];
type BillingModalDeps = Parameters<typeof createBillingModalActions>[0];
type ConnectDeps = Parameters<typeof createConnectActions>[0];
type InstallRuntimeDeps = Parameters<typeof createInstallRuntime>[0];
type NavigationDeps = Parameters<typeof createWebappNavigation>[0];
type PrimaryPayLabelDeps = Parameters<typeof createPrimaryPayActionLabel>[0];
type PromoTrialDeps = Parameters<typeof createPromoTrialActions>[0];
type TariffActionDeps = Parameters<typeof createTariffActions>[0];
type TelegramLoginDeps = Parameters<typeof createTelegramLoginActions>[0];
type PublicInstallSubscription = ReturnType<ConnectDeps["getPublicInstallSubscription"]>;

type ExternalLinkActions = {
  openAppLaunchTarget: () => void;
  openAppLink: (url: string) => void;
  openExternalLink: (url: string) => void;
  refreshAppLaunchTarget: () => void;
};

type SupportStore = {
  loadList: () => unknown;
  startPolling: (options?: { includeList?: boolean }) => unknown;
};

export type AppActionRuntimeDeps = {
  accountStore: AccountUiDeps["accountStore"];
  actionsStore: PromoTrialDeps["actionsStore"];
  adminRuntime: Pick<
    AdminPanelDeps,
    "cancelAdminAssetsPrefetch" | "ensureAdminBundle" | "ensureI18nScope"
  >;
  authStore: TelegramLoginDeps["authStore"];
  billing: AutoRenewDeps["billing"];
  billingStore: BillingModalDeps["billingStore"] &
    TariffActionDeps["billingStore"] & {
      closePaymentModal: NavigationDeps["closePaymentModal"];
    };
  canUseInstallGuides: () => boolean;
  clearLanguageClickGuard: () => void;
  demoEmail: () => string;
  devicesStore: BillingModalDeps["devicesStore"];
  externalLinkActions: ExternalLinkActions;
  getAppSettings: PrimaryPayLabelDeps["getAppSettings"];
  getDevicesEnabled: () => boolean;
  getDemoTelegramAuthPayload: TelegramLoginDeps["getDemoTelegramAuthPayload"];
  getEmailAuthEnabled: AccountUiDeps["emailAuthEnabled"];
  getIsAdmin: AdminPanelDeps["isAdmin"];
  getIsFileProtocol: AdminPanelDeps["isFileProtocol"];
  getMethods: BillingModalDeps["methods"];
  getOrigin: InstallRuntimeDeps["getOrigin"];
  getPlans: BillingModalDeps["plans"] & TariffActionDeps["getPlans"];
  getPreloadHost: InstallRuntimeDeps["getPreloadHost"];
  getRoutePathname: AdminPanelDeps["getRoutePathname"];
  getSelectedPlan: PrimaryPayLabelDeps["getSelectedPlan"];
  getSelectedTariffPlans: TariffActionDeps["getSelectedTariffPlans"];
  getSingleTariffMode: BillingModalDeps["singleTariffMode"];
  getSubscription: ConnectDeps["getSubscription"] &
    BillingModalDeps["subscription"] &
    TariffActionDeps["getSubscription"] &
    PrimaryPayLabelDeps["getSubscription"];
  getSupportEnabled: () => boolean;
  getTariffCatalog: BillingModalDeps["tariffCatalog"] & TariffActionDeps["getTariffCatalog"];
  getTariffMode: BillingModalDeps["tariffMode"];
  getTelegramNotificationsStartLink: AccountUiDeps["getTelegramNotificationsStartLink"];
  getTelegramOAuthClientId: TelegramLoginDeps["getTelegramOAuthClientId"];
  getTrafficMode: PrimaryPayLabelDeps["getTrafficMode"];
  getTrialActivationResult: ConnectDeps["getTrialActivationResult"];
  installGuidesStore: InstallRuntimeDeps["installGuidesStore"] & {
    load: (force?: boolean) => unknown;
  };
  loadData: AutoRenewDeps["loadData"];
  refreshTelegram: AccountUiDeps["refreshTelegram"];
  routePrefix: string;
  showToast: AutoRenewDeps["showToast"];
  supportStore: SupportStore;
  syncAppSectionPath: AdminPanelDeps["syncAppSectionPath"];
  t: Translate;
};

export function createAppActionRuntime({
  accountStore,
  actionsStore,
  adminRuntime,
  authStore,
  billing,
  billingStore,
  canUseInstallGuides,
  clearLanguageClickGuard,
  demoEmail,
  devicesStore,
  externalLinkActions,
  getAppSettings,
  getDevicesEnabled,
  getDemoTelegramAuthPayload,
  getEmailAuthEnabled,
  getIsAdmin,
  getIsFileProtocol,
  getMethods,
  getOrigin,
  getPlans,
  getPreloadHost,
  getRoutePathname,
  getSelectedPlan,
  getSelectedTariffPlans,
  getSingleTariffMode,
  getSubscription,
  getSupportEnabled,
  getTariffCatalog,
  getTariffMode,
  getTelegramNotificationsStartLink,
  getTelegramOAuthClientId,
  getTrafficMode,
  getTrialActivationResult,
  installGuidesStore,
  loadData,
  refreshTelegram,
  routePrefix,
  showToast,
  supportStore,
  syncAppSectionPath,
  t,
}: AppActionRuntimeDeps) {
  const isDemoAuthLogin = () => Boolean(shellState.demoAuthLogin);
  const setActiveTab = (tab: string) => {
    shellState.activeTab = tab;
  };
  const setScreen = (screen: string) => {
    shellState.screen = screen;
  };

  const telegramLoginActions = createTelegramLoginActions({
    authStore,
    getDemoTelegramAuthPayload,
    getTelegramMiniAppInitData: () => shellState.telegramMiniAppInitData,
    getTelegramOAuthClientId,
    isDemoAuthLogin,
  });

  const accountUiActions = createAccountUiActions({
    accountStore,
    demoEmail,
    emailAuthEnabled: getEmailAuthEnabled,
    getTelegram: () => shellState.tg,
    getTelegramNotificationsStartLink,
    isDemoAuthLogin,
    markTelegramNotificationsBotOpened: (openedAt) => {
      shellState.telegramNotificationsBotOpenedAt = openedAt;
    },
    openExternalLink: externalLinkActions.openExternalLink,
    refreshTelegram,
    setTelegram: (telegram) => {
      shellState.tg = telegram;
    },
    showToast,
    t,
  });

  const connectActions = createConnectActions({
    getPublicInstallSubscription: () =>
      shellState.publicInstallSubscription as PublicInstallSubscription,
    getSubscription,
    getTrialActivationResult,
    openExternalLink: externalLinkActions.openExternalLink,
    showToast,
    t,
  });

  const navigationActions = createWebappNavigation({
    canUseInstallGuides,
    closePaymentModal: () => billingStore.closePaymentModal(),
    devicesEnabled: getDevicesEnabled,
    loadDevices: () => devicesStore.loadDevices(getDevicesEnabled()),
    loadInstallGuides: () => installGuidesStore.load(),
    loadSupport: () => {
      supportStore.loadList();
      supportStore.startPolling({ includeList: true });
    },
    openConnectLink: connectActions.openConnectLink,
    setActiveTab,
    setScreen,
    supportEnabled: getSupportEnabled,
    syncSectionPath: syncAppSectionPath,
  });

  const installRuntime = createInstallRuntime({
    canUseInstallGuides,
    getOrigin,
    getPreloadHost,
    goInstall: navigationActions.goInstall,
    installGuidesStore,
    openConnectLink: connectActions.openConnectLink,
    openTrialConnectLink: connectActions.openTrialConnectLink,
    setActiveTab,
    setMode: (mode) => {
      shellState.mode = mode;
    },
    setPublicInstallSubscription: (subscription) => {
      shellState.publicInstallSubscription = subscription;
    },
    setPublicInstallToken: (token) => {
      shellState.publicInstallToken = token;
    },
    setScreen,
  });

  const billingModalActions = createBillingModalActions({
    billingStore,
    devicesEnabled: getDevicesEnabled,
    devicesStore,
    methods: getMethods,
    plans: getPlans,
    singleTariffMode: getSingleTariffMode,
    subscription: getSubscription,
    tariffCatalog: getTariffCatalog,
    tariffMode: getTariffMode,
  });

  const adminPanelActions = createAdminPanelActions({
    cancelAdminAssetsPrefetch: adminRuntime.cancelAdminAssetsPrefetch,
    clearLanguageClickGuard,
    closePaymentModal: () => billingStore.closePaymentModal(),
    ensureAdminBundle: adminRuntime.ensureAdminBundle,
    ensureI18nScope: adminRuntime.ensureI18nScope,
    getAdminActiveSection: () => shellState.adminActiveSection,
    getRoutePathname,
    getScreen: () => shellState.screen,
    isAdmin: getIsAdmin,
    isFileProtocol: getIsFileProtocol,
    routePrefix,
    setActiveTab,
    setAdminActiveSection: (section) => {
      shellState.adminActiveSection = section;
    },
    setScreen,
    showToast,
    syncAppSectionPath,
    t,
  });

  const tariffActions = createTariffActions({
    billingStore,
    getPlans,
    getSelectedTariffPlans,
    getSubscription,
    getTariffCatalog,
  });

  return {
    ...externalLinkActions,
    ...telegramLoginActions,
    ...accountUiActions,
    ...connectActions,
    ...createClipboardActions({ showToast, t }),
    ...createPromoTrialActions({ actionsStore }),
    ...createAutoRenewAction({
      billing,
      getBusy: () => shellState.autoRenewBusy,
      loadData,
      setBusy: (busy) => {
        shellState.autoRenewBusy = busy;
      },
      showToast,
      t,
    }),
    ...navigationActions,
    ...installRuntime,
    ...billingModalActions,
    ...adminPanelActions,
    ...tariffActions,
    primaryPayActionLabel: createPrimaryPayActionLabel({
      getAppSettings,
      getSelectedPlan,
      getSubscription,
      getTrafficMode,
      t,
    }),
  };
}

export type AppActionRuntime = ReturnType<typeof createAppActionRuntime>;
