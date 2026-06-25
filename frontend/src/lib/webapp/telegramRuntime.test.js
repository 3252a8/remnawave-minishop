import { describe, expect, it, vi } from "vitest";

import { createTelegramRuntime } from "./telegramRuntime.js";

function makeRuntime({ initData = "initial-init", telegram = { platform: "ios" } } = {}) {
  const state = {
    initData,
    telegram,
  };
  const setters = {
    setInitData: vi.fn((value) => {
      state.appliedInitData = value;
    }),
    setStatus: vi.fn((value) => {
      state.appliedStatus = value;
    }),
    setTelegram: vi.fn((value) => {
      state.appliedTelegram = value;
    }),
  };
  const sdk = {
    get initData() {
      return state.initData;
    },
    hasLaunchParams: vi.fn(() => true),
    load: vi.fn(async () => {
      state.telegram = { platform: "android" };
      state.initData = "loaded-init";
      return state.telegram;
    }),
    readInitDataFromLocation: vi.fn(() => "location-init"),
    refresh: vi.fn(() => {
      setters.setInitData(state.initData);
      if (state.telegram) setters.setStatus("ready");
      return state.telegram;
    }),
  };
  const createSdk = vi.fn(() => sdk);
  const runtime = createTelegramRuntime({
    actionTimeoutMs: 20,
    bootTimeoutMs: 10,
    createSdk,
    miniAppAuthTimeoutMs: 30,
    scriptUrl: "https://telegram.example/sdk.js",
    ...setters,
  });
  return { createSdk, runtime, sdk, setters, state };
}

describe("createTelegramRuntime", () => {
  it("creates the sdk and applies the initial refresh state", () => {
    const { createSdk, sdk, setters, state } = makeRuntime();

    expect(createSdk).toHaveBeenCalledWith({
      actionTimeoutMs: 20,
      bootTimeoutMs: 10,
      miniAppAuthTimeoutMs: 30,
      onInitDataChange: expect.any(Function),
      onStatusChange: setters.setStatus,
      scriptUrl: "https://telegram.example/sdk.js",
    });
    expect(sdk.refresh).toHaveBeenCalledOnce();
    expect(setters.setTelegram).toHaveBeenCalledWith(state.telegram);
    expect(setters.setStatus).toHaveBeenLastCalledWith("ready");
    expect(setters.setInitData).toHaveBeenLastCalledWith("initial-init");
  });

  it("keeps status idle when the initial refresh has no web app", () => {
    const { setters } = makeRuntime({ initData: "", telegram: null });

    expect(setters.setTelegram).toHaveBeenCalledWith(null);
    expect(setters.setStatus).toHaveBeenLastCalledWith("idle");
    expect(setters.setInitData).toHaveBeenLastCalledWith("");
  });

  it("updates telegram and init data after launch loading", async () => {
    const { runtime, setters, state } = makeRuntime();

    const loadedTelegram = await runtime.load();

    expect(loadedTelegram).toBe(state.telegram);
    expect(setters.setTelegram).toHaveBeenLastCalledWith({ platform: "android" });
    expect(setters.setInitData).toHaveBeenLastCalledWith("loaded-init");
  });

  it("proxies launch parameter and location init-data helpers", () => {
    const { runtime, sdk } = makeRuntime();

    expect(runtime.hasLaunchParams()).toBe(true);
    expect(runtime.readInitDataFromLocation()).toBe("location-init");
    expect(sdk.hasLaunchParams).toHaveBeenCalledOnce();
    expect(sdk.readInitDataFromLocation).toHaveBeenCalledOnce();
  });

  it("refreshes the shell-owned telegram binding", () => {
    const { runtime, setters, state } = makeRuntime();
    state.telegram = { platform: "desktop" };
    state.initData = "refreshed-init";

    expect(runtime.refreshTelegram()).toEqual({ platform: "desktop" });

    expect(setters.setTelegram).toHaveBeenLastCalledWith({ platform: "desktop" });
    expect(setters.setStatus).toHaveBeenLastCalledWith("ready");
    expect(setters.setInitData).toHaveBeenLastCalledWith("refreshed-init");
  });

  it("does not overwrite status on later empty refreshes", () => {
    const { runtime, setters, state } = makeRuntime();
    state.telegram = null;
    setters.setStatus.mockClear();

    expect(runtime.refreshTelegram()).toBeNull();

    expect(setters.setTelegram).toHaveBeenLastCalledWith(null);
    expect(setters.setStatus).not.toHaveBeenCalled();
  });
});
