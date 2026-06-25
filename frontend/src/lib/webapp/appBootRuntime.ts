import { publicInstallTokenFromPath } from "./routes.js";
import { refreshTelegramNotificationsAfterResume } from "./telegramNotificationsResume.js";
import { runWebappBoot } from "./webappBoot.js";

type TelegramLike = { ready?: () => void; expand?: () => void; initData?: string } | null;
type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type LoadData = (
  options?: { fresh?: boolean; preserveView?: boolean } & Record<string, unknown>
) => Promise<unknown>;

type TelegramNotificationsResumeState = {
  botOpenedAt: number;
  lastCheckAt: number;
  mode: string;
  needPrompt: boolean;
  refreshBusy: boolean;
};

type AppBootRuntimeDeps = {
  // Pre-boot short-circuits.
  loadPublicInstall: (shareToken: string) => Promise<unknown> | unknown;
  isDemoAuthMock: () => boolean;
  prepareDemoAuthState: () => void;
  // Shared / runWebappBoot environment.
  mock: unknown;
  getTelegram: () => TelegramLike;
  setMode: (mode: string) => void;
  hasTelegramLaunchParams: () => boolean;
  loadTelegramSdk: () => Promise<unknown> | unknown;
  loadData: LoadData;
  showLogin: () => void;
  clearToken: () => void;
  clearManualLogoutFlag: () => void;
  isManuallyLoggedOut: () => boolean;
  hasEmailCodeLoginDeeplink: () => boolean;
  finalizeMagicLogin: (loginToken: string) => unknown;
  finalizeTelegramAuth: (
    authData: unknown,
    source: "auth_data" | "init_data" | "id_token"
  ) => unknown;
  setAuthStatus: (message: string, isError?: boolean) => void;
  t: Translate;
  getInitDataForBoot: () => string;
  getToken: () => string;
  getCsrfToken: () => string;
  // Post-boot activation handoff.
  getMode: () => string;
  getScreen: () => string;
  continueTelegramLinkPendingAction: () => unknown;
  hasPendingActivationHandoff: () => boolean;
  maybeShowActivationSuccessDialog: (context?: Record<string, unknown>) => Promise<boolean>;
  startPendingActivationWatch: () => void;
  // Telegram-notifications resume refresh.
  telegramNotificationsResumeCooldownMs: number;
  readTelegramNotificationsResumeState: () => TelegramNotificationsResumeState;
  setTelegramNotificationsBotOpenedAt: (openedAt: number) => void;
  setTelegramNotificationsResumeLastCheckAt: (checkedAt: number) => void;
  setTelegramNotificationsResumeRefreshBusy: (busy: boolean) => void;
};

/**
 * Boot + resume glue for the webapp shell. `boot()` resolves the public-install
 * short-circuit and demo-auth mock, runs the shared boot sequence, then performs
 * the post-boot activation handoff; `refreshTelegramNotificationsOnResume()`
 * re-checks the notifications prompt when the app regains focus. Behaviour is
 * identical to the former inline functions in App.svelte — the shell passes its
 * state through getters/setters as before.
 */
export function createAppBootRuntime(deps: AppBootRuntimeDeps) {
  async function boot() {
    const shareToken = publicInstallTokenFromPath(window.location.pathname);
    if (shareToken) {
      await deps.loadPublicInstall(shareToken);
      return;
    }
    if (deps.isDemoAuthMock()) {
      deps.prepareDemoAuthState();
      deps.showLogin();
      return;
    }
    await runWebappBoot({
      MOCK: deps.mock,
      setMode: deps.setMode,
      hasTelegramLaunchParams: deps.hasTelegramLaunchParams,
      loadTelegramSdk: deps.loadTelegramSdk,
      prepareTelegramMiniApp: () => {
        const telegram = deps.getTelegram();
        if (!telegram) return;
        try {
          telegram.ready?.();
          telegram.expand?.();
        } catch (_error) {
          void _error;
        }
      },
      loadData: deps.loadData,
      showLogin: deps.showLogin,
      clearToken: deps.clearToken,
      clearManualLogoutFlag: deps.clearManualLogoutFlag,
      isManuallyLoggedOut: deps.isManuallyLoggedOut,
      hasEmailCodeLoginDeeplink: deps.hasEmailCodeLoginDeeplink,
      finalizeMagicLogin: deps.finalizeMagicLogin,
      finalizeTelegramAuth: deps.finalizeTelegramAuth,
      setAuthStatus: deps.setAuthStatus,
      t: deps.t,
      getInitDataForBoot: deps.getInitDataForBoot,
      getToken: deps.getToken,
      getCsrfToken: deps.getCsrfToken,
    });
    if (deps.getMode() === "app" && deps.getScreen() !== "admin") {
      const telegramActionHandled = await deps.continueTelegramLinkPendingAction();
      if (!telegramActionHandled) {
        if (deps.hasPendingActivationHandoff()) await deps.loadData({ fresh: true });
        const shown = await deps.maybeShowActivationSuccessDialog({ source: "boot" });
        if (!shown) deps.startPendingActivationWatch();
      }
    }
  }

  async function refreshTelegramNotificationsOnResume() {
    await refreshTelegramNotificationsAfterResume({
      cooldownMs: deps.telegramNotificationsResumeCooldownMs,
      loadData: () => deps.loadData({ fresh: true, preserveView: true }),
      readState: deps.readTelegramNotificationsResumeState,
      setBotOpenedAt: deps.setTelegramNotificationsBotOpenedAt,
      setLastCheckAt: deps.setTelegramNotificationsResumeLastCheckAt,
      setRefreshBusy: deps.setTelegramNotificationsResumeRefreshBusy,
    });
  }

  return { boot, refreshTelegramNotificationsOnResume };
}

export type AppBootRuntime = ReturnType<typeof createAppBootRuntime>;
