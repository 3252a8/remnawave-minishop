import type { AppActionRuntime } from "./appActionRuntime.js";
import type { TelegramWebApp } from "./telegramRuntime.js";

export type ShellRecord = Record<string, unknown>;

export type ShellState = {
  docsDemoParentRouteConsumed: boolean;
  telegramSdkStatus: string;
  telegramMiniAppInitData: string;
  telegramHasLaunchParams: boolean;
  mode: string;
  activeTab: string;
  screen: string;
  emailLoginDeeplinkConsumed: boolean;
  data: ShellRecord | null;
  appLaunchTarget: string;
  publicInstallSubscription: ShellRecord | null;
  publicInstallToken: string;
  autoRenewBusy: boolean;
  subscriptionReissueDialogOpen: boolean;
  subscriptionReissueBusy: boolean;
  activationSuccessDialogOpen: boolean;
  activationSuccessUseInstallGuides: boolean;
  telegramNotificationsBotOpenedAt: number;
  telegramNotificationsResumeRefreshBusy: boolean;
  telegramNotificationsResumeLastCheckAt: number;
  languageMenuOpen: boolean;
  languageClickGuard: boolean;
  languageClickGuardArmed: boolean;
  guestLanguage: string;
  emailAvatarUrl: string;
  token: string;
  csrfToken: string;
  adminBundleApi: ShellRecord | null;
  adminBundleError: string;
  adminMountTarget: HTMLElement | null;
  adminActiveSection: string;
  tg: TelegramWebApp | null;
  demoAuthLogin: unknown;
  appActions: AppActionRuntime | null;
};

export type ShellStateInit = Partial<ShellState>;

export function createInitialShellState(overrides: ShellStateInit = {}): ShellState {
  return {
    docsDemoParentRouteConsumed: false,
    telegramSdkStatus: "idle",
    telegramMiniAppInitData: "",
    telegramHasLaunchParams: false,
    mode: "loading",
    activeTab: "home",
    screen: "home",
    emailLoginDeeplinkConsumed: false,
    data: null,
    appLaunchTarget: "",
    publicInstallSubscription: null,
    publicInstallToken: "",
    autoRenewBusy: false,
    subscriptionReissueDialogOpen: false,
    subscriptionReissueBusy: false,
    activationSuccessDialogOpen: false,
    activationSuccessUseInstallGuides: false,
    telegramNotificationsBotOpenedAt: 0,
    telegramNotificationsResumeRefreshBusy: false,
    telegramNotificationsResumeLastCheckAt: 0,
    languageMenuOpen: false,
    languageClickGuard: false,
    languageClickGuardArmed: false,
    guestLanguage: "",
    emailAvatarUrl: "",
    token: "",
    csrfToken: "",
    adminBundleApi: null,
    adminBundleError: "",
    adminMountTarget: null,
    adminActiveSection: "stats",
    tg: null,
    demoAuthLogin: false,
    appActions: null,
    ...overrides,
  };
}

export function createShellState(overrides: ShellStateInit = {}): ShellState {
  const state = $state(createInitialShellState(overrides));
  return state;
}

export const shellState = createShellState();

export function resetShellState(overrides: ShellStateInit = {}): ShellState {
  Object.assign(shellState, createInitialShellState(overrides));
  return shellState;
}
