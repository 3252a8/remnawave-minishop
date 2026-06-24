import { describe, expect, it, vi } from "vitest";

import { createTelegramLoginActions } from "./telegramLoginActions.js";

function makeActions(overrides = {}) {
  const state = {
    demoAuthLogin: false,
    initData: "init-data",
    oauthClientId: 123,
    payload: { id: 42 },
    ...overrides.state,
  };
  const authStore = {
    finalizeTelegramAuth: vi.fn(async () => true),
    openTelegramLogin: vi.fn(async () => true),
    ...overrides.authStore,
  };
  const actions = createTelegramLoginActions({
    authStore,
    getDemoTelegramAuthPayload: () => state.payload,
    getTelegramMiniAppInitData: () => state.initData,
    getTelegramOAuthClientId: () => state.oauthClientId,
    isDemoAuthLogin: () => state.demoAuthLogin,
  });
  return { actions, authStore, state };
}

describe("createTelegramLoginActions", () => {
  it("finalizes demo telegram auth directly", async () => {
    const { actions, authStore, state } = makeActions({
      state: { demoAuthLogin: true },
    });

    await actions.openLoginTelegram();

    expect(authStore.finalizeTelegramAuth).toHaveBeenCalledWith(state.payload, "auth_data");
    expect(authStore.openTelegramLogin).not.toHaveBeenCalled();
  });

  it("starts regular telegram login with live init data", async () => {
    const { actions, authStore, state } = makeActions();

    await actions.openLoginTelegram();

    expect(authStore.openTelegramLogin).toHaveBeenCalledWith(123, expect.any(Function));
    const readInitData = authStore.openTelegramLogin.mock.calls[0][1];

    state.initData = "fresh-init-data";

    expect(readInitData()).toBe("fresh-init-data");
    expect(authStore.finalizeTelegramAuth).not.toHaveBeenCalled();
  });
});
