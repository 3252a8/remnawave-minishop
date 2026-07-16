import { describe, expect, it, vi } from "vitest";

import { formatTemplate } from "../../webapp/formatters.js";
import { createUsersStore } from "./usersStore.js";

function makeStore(api = vi.fn()) {
  return createUsersStore({
    api,
    onToast: vi.fn(),
    at: (key, _params = {}, fallback = key) => fallback,
  });
}

describe("usersStore", () => {
  it("loads users with page, filter and sorting parameters", async () => {
    const api = vi.fn().mockResolvedValue({ ok: true, users: [{ user_id: 42 }], total: 1 });
    const store = makeStore(api);

    store.updateState({
      usersPage: 1,
      usersQuery: " ivan ",
      usersFilter: "active",
      usersPanelStatus: "enabled",
      usersPremiumTraffic: "with",
      usersSort: "created_desc",
    });

    await store.loadUsers();

    expect(api).toHaveBeenCalledWith(
      "/admin/users?page=1&page_size=25&q=ivan&filter=active&panel_status=enabled&premium_traffic=with&sort=created_desc"
    );
    expect(store).toMatchObject({
      users: [{ user_id: 42 }],
      usersTotal: 1,
      usersLoading: false,
    });
  });

  it("opens user details and derives editable subscription drafts", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      user: { user_id: 7, first_name: "Ann" },
      active_subscription: {
        tariff_key: "pro",
        premium_unlimited_override: true,
        premium_bonus_bytes: 2 * 1024 ** 3,
        regular_unlimited_override: false,
        regular_bonus_bytes: 512 * 1024 ** 2,
        hwid_device_limit: 0,
      },
    });
    const store = makeStore(api);

    await store.openUser(7, { skipPush: true });

    expect(api).toHaveBeenCalledWith("/admin/users/7");
    expect(store).toMatchObject({
      openedUser: { user_id: 7, first_name: "Ann" },
      userDetailLoading: false,
      userExtendTariffKey: "pro",
      userTariffActionKey: "pro",
      premiumUnlimitedDraft: true,
      premiumBonusGbDraft: 2,
      regularUnlimitedDraft: false,
      regularBonusGbDraft: 0.5,
      hwidUnlimitedDraft: true,
      hwidDeviceLimitDraft: "",
    });
  });

  it("closes user modal and clears nested detail state", async () => {
    const api = vi.fn().mockResolvedValue({ ok: true, user: { user_id: 9 } });
    const store = makeStore(api);

    await store.openUser({ user_id: 9 }, { skipPush: true });
    store.updateState({ userMessageDraft: "hello", userReferralsOpen: true });
    store.closeUser({ skipPush: true });

    expect(store).toMatchObject({
      openedUser: null,
      openedUserDetail: null,
      userMessageDraft: "",
      userReferralsOpen: false,
      userLogsLoaded: false,
    });
  });

  it("sends tariff HWID reset choice when changing a user tariff", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce({ ok: true })
      .mockResolvedValueOnce({ ok: true, user: { user_id: 42 }, active_subscription: null });
    const store = makeStore(api);
    store.updateState({
      openedUser: { user_id: 42 },
      userTariffActionKey: "pro",
      userApplyTariffHwidLimit: true,
    });

    await store.changeUserTariff();

    expect(api).toHaveBeenNthCalledWith(1, "/admin/users/42/tariff", {
      method: "POST",
      body: JSON.stringify({ tariff_key: "pro", apply_tariff_hwid_limit: true }),
    });
    expect(store.userApplyTariffHwidLimit).toBe(false);
  });

  it("shows traffic grant toasts with interpolated user identity", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce({ ok: true })
      .mockResolvedValueOnce({
        ok: true,
        user: { user_id: 77, first_name: "Ann", last_name: "Lee", username: "ann" },
        active_subscription: null,
      });
    const onToast = vi.fn();
    const at = vi.fn((key, params = {}, fallback = key) =>
      formatTemplate(
        key === "traffic_grant_premium_done"
          ? "+{gb} GB premium granted to {user} (ID: {user_id})"
          : fallback,
        params
      )
    );
    const store = createUsersStore({ api, onToast, at });

    store.updateState({
      openedUser: { user_id: 77, first_name: "Ann", last_name: "Lee", username: "ann" },
      grantTrafficGbDraft: "25",
      grantTrafficKindDraft: "premium",
    });

    await store.grantTraffic();

    expect(api).toHaveBeenNthCalledWith(1, "/admin/users/77/traffic-grant", {
      method: "POST",
      body: JSON.stringify({ kind: "premium", gb: 25 }),
    });
    expect(at).toHaveBeenCalledWith(
      "traffic_grant_premium_done",
      { gb: 25, user_id: "77", user: "Ann Lee" },
      "✅ +{gb} GB of premium traffic granted to {user} (ID: {user_id})"
    );
    expect(onToast).toHaveBeenCalledWith("+25 GB premium granted to Ann Lee (ID: 77)");
    expect(onToast.mock.calls[0][0]).not.toContain("{user_id}");
  });
});
