import { describe, expect, it, vi } from "vitest";

import { createDevicesStore } from "./devicesStore.js";

function makeDevicesStore(api = vi.fn()) {
  const deps = {
    api,
    t: (key: string) => key,
    showToast: vi.fn(),
  };
  return { store: createDevicesStore(deps), deps };
}

describe("devicesStore", () => {
  it("refreshes the devices payload after a successful disconnect", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        current_devices: 1,
        max_devices: 3,
        devices: [{ token: "device-token", display_name: "Phone" }],
      })
      .mockResolvedValueOnce({ ok: true })
      .mockResolvedValueOnce({
        ok: true,
        current_devices: 0,
        max_devices: 3,
        devices: [],
      });
    const { store, deps } = makeDevicesStore(api);

    await store.loadDevices(true);
    store.openDeviceDisconnectDialog({
      token: "device-token",
      display_name: "Phone",
    } as unknown as Parameters<typeof store.openDeviceDisconnectDialog>[0]);
    await store.disconnectDevice(true);

    expect(api).toHaveBeenNthCalledWith(1, "/devices");
    expect(api).toHaveBeenNthCalledWith(2, "/devices/disconnect", {
      method: "POST",
      body: JSON.stringify({ token: "device-token" }),
    });
    expect(api).toHaveBeenNthCalledWith(3, "/devices");
    expect(store.devicesData).toMatchObject({ current_devices: 0, devices: [] });
    expect(store.deviceConfirmOpen).toBe(false);
    expect(store.deviceToDisconnect).toBe(null);
    expect(deps.showToast).toHaveBeenCalledWith("wa_device_disconnected");
  });

  it("saves a device name and patches the listed device in place", async () => {
    const renamed = {
      token: "device-token",
      display_name: "Work laptop",
      custom_name: "Work laptop",
      default_name: "Laptop",
    };
    const api = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        current_devices: 2,
        max_devices: 3,
        devices: [
          { token: "device-token", display_name: "Laptop" },
          { token: "other-token", display_name: "Phone" },
        ],
      })
      .mockResolvedValueOnce({ ok: true, device: renamed });
    const { store, deps } = makeDevicesStore(api);

    await store.loadDevices(true);
    store.openDeviceRenameDialog({
      token: "device-token",
      display_name: "Laptop",
    } as unknown as Parameters<typeof store.openDeviceRenameDialog>[0]);
    store.deviceRenameValue = "  Work\n laptop ";
    await store.renameDevice();

    expect(api).toHaveBeenCalledTimes(2);
    expect(api).toHaveBeenNthCalledWith(2, "/devices/rename", {
      method: "POST",
      body: JSON.stringify({ token: "device-token", name: "Work laptop" }),
    });
    expect(store.devicesData?.devices?.[0]).toMatchObject(renamed);
    expect(store.devicesData?.devices?.[1]).toMatchObject({ token: "other-token" });
    expect(store.deviceRenameOpen).toBe(false);
    expect(deps.showToast).toHaveBeenCalledWith("wa_device_renamed");
  });

  it("keeps the dialog open without calling the API when the name is too long", async () => {
    const api = vi.fn();
    const { store } = makeDevicesStore(api);

    store.openDeviceRenameDialog({
      token: "device-token",
    } as unknown as Parameters<typeof store.openDeviceRenameDialog>[0]);
    store.deviceRenameValue = "x".repeat(33);
    await store.renameDevice();

    expect(api).not.toHaveBeenCalled();
    expect(store.deviceRenameOpen).toBe(true);
    expect(store.deviceRenameError).toBe("wa_device_name_too_long");
  });

  it("restores the default name and reports failures inside the dialog", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        device: { token: "device-token", display_name: "Laptop", custom_name: null },
      })
      .mockResolvedValueOnce({ ok: false, error: "device_not_found" });
    const { store, deps } = makeDevicesStore(api);
    const device = {
      token: "device-token",
      custom_name: "Old name",
    } as unknown as Parameters<typeof store.openDeviceRenameDialog>[0];

    store.openDeviceRenameDialog(device);
    expect(store.deviceRenameValue).toBe("Old name");
    await store.renameDevice("");
    expect(api).toHaveBeenNthCalledWith(1, "/devices/rename", {
      method: "POST",
      body: JSON.stringify({ token: "device-token", name: "" }),
    });
    expect(deps.showToast).toHaveBeenCalledWith("wa_device_name_restored");

    store.openDeviceRenameDialog(device);
    await store.renameDevice("New name");
    expect(store.deviceRenameError).toBe("wa_device_rename_failed");
    expect(store.deviceRenameOpen).toBe(true);
  });
});
