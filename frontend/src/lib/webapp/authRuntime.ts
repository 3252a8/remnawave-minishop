import { readEmailCodeLoginDeeplink } from "./deeplinks.js";
import { isPasswordLoginPath, syncPasswordLoginPath } from "./passwordLoginRoute.js";
import { shellState } from "./shellState.svelte";
import { rememberInstallAuthDestination } from "./installAuthDestination.js";
import type { AuthState } from "./stores/authStore";

type AuthStoreLike = {
  clearPendingEmailCode: () => void;
  requestEmailCode: (setScreen: (screen: string) => void) => unknown;
  restorePendingEmailCode: (setScreen: (screen: string) => void) => unknown;
  update: (updater: (state: AuthState) => AuthState) => void;
};

type AuthRuntimeDeps = {
  authStore: AuthStoreLike;
  cleanDocsDemoRouteQuery: () => void;
  isDocsDemo: boolean;
  readEmailCodeLoginDeeplink?: () => string | null;
  routePathnameFromLocation: () => string;
  routePrefix: string;
  syncPasswordLoginPath?: typeof syncPasswordLoginPath;
  tick: () => Promise<void>;
};

export function createAuthRuntime({
  authStore,
  cleanDocsDemoRouteQuery,
  isDocsDemo,
  readEmailCodeLoginDeeplink: readEmailDeeplink = readEmailCodeLoginDeeplink,
  routePathnameFromLocation,
  routePrefix,
  syncPasswordLoginPath: syncPasswordPath = syncPasswordLoginPath,
  tick,
}: AuthRuntimeDeps) {
  const setScreen = (screen: string) => {
    shellState.screen = screen;
  };

  function setPasswordLoginMode(enabled: boolean, replace = false) {
    const nextEnabled = Boolean(enabled);
    authStore.update((state) => ({
      ...state,
      passwordLoginMode: nextEnabled,
      passwordLoginFallback: false,
      authStatus: "",
      authIsError: false,
    }));
    syncPasswordPath({
      cleanDocsDemoRouteQuery,
      enabled: nextEnabled,
      isDocsDemo,
      replace,
      routePrefix,
    });
  }

  async function startEmailCodeLoginFromDeeplink() {
    if (shellState.emailLoginDeeplinkConsumed) return;
    const emailHint = readEmailDeeplink();
    if (!emailHint) return;
    shellState.emailLoginDeeplinkConsumed = true;
    authStore.clearPendingEmailCode();
    authStore.update((state) => ({
      ...state,
      email: emailHint,
      emailCode: "",
      pendingEmail: "",
      passwordLoginMode: false,
      passwordLoginFallback: false,
    }));
    await tick();
    await authStore.requestEmailCode(setScreen);
  }

  function showLogin() {
    rememberInstallAuthDestination("login");
    shellState.mode = "login";
    setScreen("login");
    shellState.activeTab = "home";
    setPasswordLoginMode(isPasswordLoginPath(routePathnameFromLocation()), true);
    authStore.restorePendingEmailCode(setScreen);
    void startEmailCodeLoginFromDeeplink();
  }

  function submitEmailOnEnter(event: KeyboardEvent) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    authStore.requestEmailCode(setScreen);
  }

  return {
    setPasswordLoginMode,
    showLogin,
    startEmailCodeLoginFromDeeplink,
    submitEmailOnEnter,
  };
}
