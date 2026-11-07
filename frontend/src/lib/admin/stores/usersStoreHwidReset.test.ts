import { describe, expect, it, vi } from "vitest";
import en from "../../../../../locales/en.json";
import ru from "../../../../../locales/ru.json";
import { createUsersStore } from "./usersStore.js";

const translations: Record<string, string> = en;

const subscription = {
  hwid_device_limit: 3,
  extra_hwid_devices: 2,
  subscription_url: "https://example.test/subscription/original",
};
const detail = (count = 5) => ({
  ok: true,
  user: { user_id: 7 },
  active_subscription: { ...subscription },
  subscriptions: [],
  hwid_devices: { current_devices: count, max_devices: 5 },
});

function makeStore(api = vi.fn()) {
  const onToast = vi.fn();
  const store = createUsersStore({
    api,
    onToast,
    at: (key, _params = {}, fallback = key) => translations[`admin_${key}`] || fallback,
  });
  return { store, onToast };
}

describe("admin HWID reset", () => {
  it("clears recorded devices, refreshes usage and keeps subscription and draft limits", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce(detail())
      .mockResolvedValueOnce({ ok: true })
      .mockResolvedValueOnce(detail(0));
    const { store, onToast } = makeStore(api);
    await store.openUser(7, { skipPush: true });
    store.updateState({ hwidDeviceLimitDraft: 9, userExtendDays: 60 });

    expect(await store.resetHwidDevicesUser()).toBe(true);

    expect(api).toHaveBeenNthCalledWith(2, "/admin/users/7/hwid-devices/reset", { method: "POST" });
    expect(api).toHaveBeenNthCalledWith(3, "/admin/users/7");
    expect(store.openedUserDetail?.hwid_devices).toEqual({ current_devices: 0, max_devices: 5 });
    expect(store.openedUserDetail?.active_subscription).toEqual(subscription);
    expect(store.hwidDeviceLimitDraft).toBe(9);
    expect(store.userExtendDays).toBe(60);
    expect(store.userActionBusy).toBe(false);
    expect(onToast).toHaveBeenCalledWith("Recorded devices cleared");
  });

  it("does not submit with no selected user or while another action is running", async () => {
    const api = vi.fn().mockResolvedValue(detail());
    const { store } = makeStore(api);
    expect(await store.resetHwidDevicesUser()).toBe(false);
    expect(api).not.toHaveBeenCalled();
    await store.openUser(7, { skipPush: true });
    api.mockClear();
    store.updateState({ userActionBusy: true });
    expect(await store.resetHwidDevicesUser()).toBe(false);
    expect(api).not.toHaveBeenCalled();
  });

  it("prevents duplicate submissions while the reset request is in flight", async () => {
    let resolveReset!: (response: { ok: true }) => void;
    const pending = new Promise<{ ok: true }>((resolve) => {
      resolveReset = resolve;
    });
    const api = vi
      .fn()
      .mockResolvedValueOnce(detail())
      .mockReturnValueOnce(pending)
      .mockResolvedValueOnce(detail(0));
    const { store } = makeStore(api);
    await store.openUser(7, { skipPush: true });
    const reset = store.resetHwidDevicesUser();
    expect(store.userActionBusy).toBe(true);
    expect(await store.resetHwidDevicesUser()).toBe(false);
    expect(api).toHaveBeenCalledTimes(2);
    resolveReset({ ok: true });
    await reset;
    expect(store.userActionBusy).toBe(false);
  });

  it("reports panel failure and refreshes a partially cleared device count", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce(detail())
      .mockResolvedValueOnce({ ok: false, error: "panel_hwid_reset_failed" })
      .mockResolvedValueOnce(detail(2));
    const { store, onToast } = makeStore(api);
    await store.openUser(7, { skipPush: true });
    expect(await store.resetHwidDevicesUser()).toBe(false);
    expect(store.openedUserDetail?.hwid_devices?.current_devices).toBe(2);
    expect(store.userActionBusy).toBe(false);
    expect(onToast).not.toHaveBeenCalledWith("Recorded devices cleared");
    expect(onToast).toHaveBeenCalledWith(en.admin_user_hwid_reset_failed);
  });

  it("releases the busy state after a transport error", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce(detail())
      .mockRejectedValueOnce(new Error("Network error"))
      .mockResolvedValueOnce(detail());
    const { store, onToast } = makeStore(api);
    await store.openUser(7, { skipPush: true });
    expect(await store.resetHwidDevicesUser()).toBe(false);
    expect(store.userActionBusy).toBe(false);
    expect(onToast).not.toHaveBeenCalledWith("Recorded devices cleared");
  });

  it("provides all reset messages in both base locales", () => {
    const keys = [
      "admin_user_hwid_reset",
      "admin_user_hwid_reset_hint",
      "admin_user_hwid_reset_confirm_title",
      "admin_user_hwid_reset_confirm_description",
      "admin_user_hwid_reset_success",
      "admin_user_hwid_reset_failed",
    ] as const;
    for (const key of keys) {
      expect(en[key]).toBeTruthy();
      expect(ru[key]).toBeTruthy();
    }
  });
});
