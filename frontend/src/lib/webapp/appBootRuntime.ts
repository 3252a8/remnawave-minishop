import { publicInstallTokenFromPath } from "./routes.js";
import { shellState } from "./shellState.svelte";
import { refreshTelegramNotificationsAfterResume } from "./telegramNotificationsResume.js";
import { runWebappBoot } from "./webappBoot.js";

type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type LoadData = (
  options?: { fresh?: boolean; preserveView?: boolean } & Record<string, unknown>
) => Promise<unknown>;

type AppBootRuntimeDeps = {
  // Pre-boot short-circuits.
  loadPublicInstall: (shareToken: string) => Promise<unknown> | unknown;
  isDemoAuthMock: () => boolean;
  prepareDemoAuthState: () => void;
  // Shared / runWebappBoot environment.
  mock: unknown;
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
  readTelegramMiniAppInitDataFromLocation: () => string;
  // Post-boot activation handoff.
  continueTelegramLinkPendingAction: () => unknown;
  hasPendingActivationHandoff: () => boolean;
  maybeShowActivationSuccessDialog: (context?: Record<string, unknown>) => Promise<boolean>;
  startPendingActivationWatch: () => void;
  // Telegram-notifications resume refresh.
  telegramNotificationsResumeCooldownMs: number;
  getTelegramNotificationsNeedPrompt: () => boolean;
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
      setMode: (mode: string) => {
        shellState.mode = mode;
      },
      hasTelegramLaunchParams: deps.hasTelegramLaunchParams,
      loadTelegramSdk: deps.loadTelegramSdk,
      prepareTelegramMiniApp: () => {
        const telegram = shellState.tg;
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
      getInitDataForBoot: () =>
        shellState.telegramMiniAppInitData ||
        shellState.tg?.initData ||
        deps.readTelegramMiniAppInitDataFromLocation(),
      getToken: () => shellState.token,
      getCsrfToken: () => shellState.csrfToken,
    });
    if (shellState.mode === "app" && shellState.screen !== "admin") {
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
      readState: () => ({
        botOpenedAt: shellState.telegramNotificationsBotOpenedAt,
        lastCheckAt: shellState.telegramNotificationsResumeLastCheckAt,
        mode: shellState.mode,
        needPrompt: deps.getTelegramNotificationsNeedPrompt(),
        refreshBusy: shellState.telegramNotificationsResumeRefreshBusy,
      }),
      setBotOpenedAt: (openedAt) => {
        shellState.telegramNotificationsBotOpenedAt = openedAt;
      },
      setLastCheckAt: (checkedAt) => {
        shellState.telegramNotificationsResumeLastCheckAt = checkedAt;
      },
      setRefreshBusy: (busy) => {
        shellState.telegramNotificationsResumeRefreshBusy = busy;
      },
    });
  }

  return { boot, refreshTelegramNotificationsOnResume };
}

export type AppBootRuntime = ReturnType<typeof createAppBootRuntime>;
