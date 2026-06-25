import {
  clearManualLogoutFlag as clearManualLogoutFlagInStorage,
  clearStoredToken,
  isManuallyLoggedOut as readManualLogoutFlag,
  markManualLogout as markManualLogoutInStorage,
  readCookie,
} from "./session.js";

type SessionStorageActions = {
  clearManualLogoutFlag: (flagKey: string) => void;
  clearStoredToken: () => void;
  isManuallyLoggedOut: (flagKey: string) => boolean;
  markManualLogout: (flagKey: string) => void;
  readCookie: (name: string) => string;
};

type WebappSessionActionDeps = {
  csrfCookieName: string;
  isMock: () => boolean;
  manualLogoutFlagKey: string;
  setCsrfToken: (token: string) => void;
  setToken: (token: string) => void;
  storage?: SessionStorageActions;
};

const defaultStorage: SessionStorageActions = {
  clearManualLogoutFlag: clearManualLogoutFlagInStorage,
  clearStoredToken,
  isManuallyLoggedOut: readManualLogoutFlag,
  markManualLogout: markManualLogoutInStorage,
  readCookie,
};

export function createWebappSessionActions({
  csrfCookieName,
  isMock,
  manualLogoutFlagKey,
  setCsrfToken,
  setToken,
  storage = defaultStorage,
}: WebappSessionActionDeps) {
  function clearManualLogoutFlag() {
    storage.clearManualLogoutFlag(manualLogoutFlagKey);
  }

  function updateToken(nextToken: string, nextCsrf = "") {
    clearManualLogoutFlag();
    setToken(nextToken || "");
    setCsrfToken(nextCsrf || storage.readCookie(csrfCookieName) || "");
    if (!isMock()) storage.clearStoredToken();
  }

  function clearToken() {
    setToken("");
    setCsrfToken("");
    storage.clearStoredToken();
  }

  function markManualLogout() {
    storage.markManualLogout(manualLogoutFlagKey);
  }

  function isManuallyLoggedOut() {
    return storage.isManuallyLoggedOut(manualLogoutFlagKey);
  }

  return {
    clearManualLogoutFlag,
    clearToken,
    isManuallyLoggedOut,
    markManualLogout,
    setToken: updateToken,
  };
}
