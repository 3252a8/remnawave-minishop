import { readEmailCodeLoginDeeplink } from "./deeplinks.js";
import { isPasswordLoginPath, syncPasswordLoginPath } from "./passwordLoginRoute.js";
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
  getEmailLoginDeeplinkConsumed: () => boolean;
  isDocsDemo: boolean;
  readEmailCodeLoginDeeplink?: () => string | null;
  routePathnameFromLocation: () => string;
  routePrefix: string;
  setActiveTab: (tab: string) => void;
  setEmailLoginDeeplinkConsumed: (consumed: boolean) => void;
  setMode: (mode: string) => void;
  setScreen: (screen: string) => void;
  syncPasswordLoginPath?: typeof syncPasswordLoginPath;
  tick: () => Promise<void>;
};

export function createAuthRuntime({
  authStore,
  cleanDocsDemoRouteQuery,
  getEmailLoginDeeplinkConsumed,
  isDocsDemo,
  readEmailCodeLoginDeeplink: readEmailDeeplink = readEmailCodeLoginDeeplink,
  routePathnameFromLocation,
  routePrefix,
  setActiveTab,
  setEmailLoginDeeplinkConsumed,
  setMode,
  setScreen,
  syncPasswordLoginPath: syncPasswordPath = syncPasswordLoginPath,
  tick,
}: AuthRuntimeDeps) {
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
    if (getEmailLoginDeeplinkConsumed()) return;
    const emailHint = readEmailDeeplink();
    if (!emailHint) return;
    setEmailLoginDeeplinkConsumed(true);
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
    setMode("login");
    setScreen("login");
    setActiveTab("home");
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
