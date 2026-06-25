import { describe, expect, it, vi } from "vitest";

import { createSectionDataLoader } from "./sectionDataLoader.js";

function makeLoader() {
  const deps = {
    devicesStore: { loadDevices: vi.fn(async () => {}) },
    installGuidesStore: { load: vi.fn(async () => {}) },
    supportStore: {
      loadList: vi.fn(async () => {}),
      openTicket: vi.fn(async () => {}),
      startPolling: vi.fn(),
    },
  };
  return { deps, loader: createSectionDataLoader(deps) };
}

describe("createSectionDataLoader", () => {
  it("force-loads devices only when the section is devices and devices are enabled", async () => {
    const { deps, loader } = makeLoader();

    await loader.loadSectionData({
      initialSupportTicketId: null,
      installGuidesPromise: null,
      payload: { settings: { my_devices_enabled: true } },
      section: "devices",
    });

    expect(deps.devicesStore.loadDevices).toHaveBeenCalledWith(true, true);
  });

  it("does not load devices when devices are disabled", async () => {
    const { deps, loader } = makeLoader();

    await loader.loadSectionData({
      initialSupportTicketId: null,
      installGuidesPromise: null,
      payload: { settings: { my_devices_enabled: false } },
      section: "devices",
    });

    expect(deps.devicesStore.loadDevices).not.toHaveBeenCalled();
  });

  it("awaits the preloaded install-guides promise on the install section", async () => {
    const { deps, loader } = makeLoader();
    const preload = Promise.resolve("preloaded");

    await loader.loadSectionData({
      initialSupportTicketId: null,
      installGuidesPromise: preload,
      payload: { settings: {} },
      section: "install",
    });

    // The preloaded promise satisfies the install await, so no extra store load fires.
    expect(deps.installGuidesStore.load).not.toHaveBeenCalled();
  });

  it("loads install guides directly on the install section when no preload exists", async () => {
    const { deps, loader } = makeLoader();

    await loader.loadSectionData({
      initialSupportTicketId: null,
      installGuidesPromise: null,
      payload: { settings: {} },
      section: "install",
    });

    expect(deps.installGuidesStore.load).toHaveBeenCalledOnce();
  });

  it("background-loads install guides on other sections when guides are available", async () => {
    const { deps, loader } = makeLoader();

    await loader.loadSectionData({
      initialSupportTicketId: null,
      installGuidesPromise: null,
      payload: {
        settings: { subscription_guides_enabled: true },
        subscription: { active: true },
      },
      section: "home",
    });

    expect(deps.installGuidesStore.load).toHaveBeenCalledOnce();
  });

  it("does not background-load install guides when the subscription is inactive", async () => {
    const { deps, loader } = makeLoader();

    await loader.loadSectionData({
      initialSupportTicketId: null,
      installGuidesPromise: null,
      payload: {
        settings: { subscription_guides_enabled: true },
        subscription: { active: false },
      },
      section: "home",
    });

    expect(deps.installGuidesStore.load).not.toHaveBeenCalled();
  });

  it("opens the deep-linked support ticket and starts list polling", async () => {
    const { deps, loader } = makeLoader();

    await loader.loadSectionData({
      initialSupportTicketId: 42,
      installGuidesPromise: null,
      payload: { settings: {} },
      section: "support",
    });

    expect(deps.supportStore.openTicket).toHaveBeenCalledWith(42, { skipPush: true });
    expect(deps.supportStore.loadList).not.toHaveBeenCalled();
    expect(deps.supportStore.startPolling).toHaveBeenCalledWith({ includeList: true });
  });

  it("loads the support list when no ticket is deep-linked", async () => {
    const { deps, loader } = makeLoader();

    await loader.loadSectionData({
      initialSupportTicketId: null,
      installGuidesPromise: null,
      payload: { settings: {} },
      section: "support",
    });

    expect(deps.supportStore.loadList).toHaveBeenCalledOnce();
    expect(deps.supportStore.openTicket).not.toHaveBeenCalled();
    expect(deps.supportStore.startPolling).toHaveBeenCalledWith({ includeList: true });
  });
});
