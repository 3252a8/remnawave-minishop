import {
  clearManualLogoutFlag as clearManualLogoutFlagInStorage,
  clearStoredToken,
  isManuallyLoggedOut as readManualLogoutFlag,
  markManualLogout as markManualLogoutInStorage,
  readCookie,
} from "./session.js";
import { shellState } from "./shellState.svelte";
import { clearEmojiPreviewStorage } from "./emojiPreviewStorage";

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
  storage = defaultStorage,
}: WebappSessionActionDeps) {
  function clearManualLogoutFlag() {
    storage.clearManualLogoutFlag(manualLogoutFlagKey);
  }

  function updateToken(nextToken: string, nextCsrf = "") {
    clearManualLogoutFlag();
    shellState.token = nextToken || "";
    shellState.csrfToken = nextCsrf || storage.readCookie(csrfCookieName) || "";
    if (!isMock()) storage.clearStoredToken();
  }

  function clearToken() {
    shellState.token = "";
    shellState.csrfToken = "";
    storage.clearStoredToken();
  }

  function markManualLogout() {
    void clearEmojiPreviewStorage();
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
