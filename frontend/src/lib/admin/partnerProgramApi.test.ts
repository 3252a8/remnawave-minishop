import { describe, expect, it, vi } from "vitest";

import { partnerTopListQuery } from "./partnerProgramUi.js";
import type { AdminApi } from "../../admin/adminStores.js";
import {
  DEFAULT_PARTNER_LIST_QUERY,
  loadPartnerDashboard,
  loadPartnerDetail,
  loadPartnerView,
  loadPartnerWorkspaceCounts,
  loadPartnerPage,
  mapApplication,
  mapPartner,
  mapWithdrawal,
  PARTNER_LIST_PAGE_SIZE,
  requirePartnerAdminResponse,
} from "./partnerProgramApi.js";

describe("partner program admin API", () => {
  it("opens the dashboard with bounded activity and top partners only", async () => {
    const api = vi.fn(async (path: string) =>
      path.includes("/overview?")
        ? {
            counts: {
              pending_applications: 257,
              open_withdrawals: 8,
              has_applications: true,
              referral_program_enabled: false,
            },
            applications: [{ application_id: 42, user_id: 21, status: "pending" }],
            withdrawals: [
              { withdrawal_id: 7, user_id: 34, partner_id: 12, display_label: "Alice" },
            ],
          }
        : { partners: [{ partner_id: 12 }], total: 25 }
    );
    const result = await loadPartnerView(
      api as unknown as AdminApi,
      "dashboard",
      "RUB",
      "",
      DEFAULT_PARTNER_LIST_QUERY,
      partnerTopListQuery("earned_desc")
    );
    expect(api.mock.calls.map(([path]) => path)).toEqual([
      "/admin/partners/overview?currency=RUB&days=all&activity=1",
      "/admin/partners?currency=RUB&limit=6&offset=0&sort=earned_desc",
    ]);
    expect(result).toMatchObject({
      view: "dashboard",
      dashboard: {
        counts: {
          pendingApplications: 257,
          openWithdrawals: 8,
          hasApplications: true,
          referralProgramEnabled: false,
        },
        pendingApplications: [{ id: "42" }],
        recentWithdrawals: [{ id: "7", partner: "Alice", handle: "#34" }],
      },
      top: { partners: [{ id: "12" }], total: 25 },
    });
  });

  it.each([
    ["partners", "/admin/partners?currency=USD&limit=25&offset=0&sort=clients_desc"],
    ["applications", "/admin/partner-applications?limit=200"],
    ["withdrawals", "/admin/partner-withdrawals?currency=USD&limit=200"],
    ["partner_detail", "/admin/partners/453?currency=USD"],
    ["application_detail", "/admin/partner-applications/453"],
    ["withdrawal_detail", "/admin/partner-withdrawals/453"],
  ] as const)("requests only the selected %s view", async (view, path) => {
    const api = vi.fn().mockResolvedValue({});
    await loadPartnerView(
      api as unknown as AdminApi,
      view,
      "USD",
      "453",
      DEFAULT_PARTNER_LIST_QUERY,
      partnerTopListQuery("earned_desc")
    );
    expect(api.mock.calls).toEqual([[path]]);
  });

  it("loads currency-scoped tab badges without fetching lists on a deep link", async () => {
    const api = vi.fn().mockResolvedValue({ pending_applications: 258, open_withdrawals: 301 });
    const counts = await loadPartnerWorkspaceCounts(api as unknown as AdminApi, "EUR");
    expect(counts).toMatchObject({ pendingApplications: 258, openWithdrawals: 301 });
    expect(api.mock.calls).toEqual([["/admin/partners/attention?currency=EUR"]]);
  });

  it("requests the selected server-side page and sort order", async () => {
    const request = vi.fn().mockResolvedValue({
      partners: [
        {
          partner_id: 12,
          user_id: 34,
          display_label: "Partner",
          status: "active",
          commission_bps: 3000,
          clients_count: 7,
          balances: [],
        },
      ],
      total: 5781,
    });

    const result = await loadPartnerPage(request as unknown as AdminApi, "RUB", {
      page: 2,
      search: "  34  ",
      status: "active",
      sort: "clients_desc",
    });

    const path = String(request.mock.calls[0][0]);
    const query = new URLSearchParams(path.split("?")[1]);
    expect(query.get("limit")).toBe(String(PARTNER_LIST_PAGE_SIZE));
    expect(query.get("offset")).toBe(String(PARTNER_LIST_PAGE_SIZE * 2));
    expect(query.get("search")).toBe("34");
    expect(query.get("status")).toBe("active");
    expect(query.get("sort")).toBe("clients_desc");
    expect(result.total).toBe(5781);
    expect(result.partners[0].clients).toBe(7);
  });

  it("maps the current user identity for partner rows", async () => {
    const request = vi.fn().mockResolvedValue({
      partners: [
        {
          partner_id: 12,
          user_id: 34,
          display_label: "Alice Partner",
          username: "alice",
          avatar_url: "/api/admin/users/34/avatar?v=1",
          status: "active",
          commission_bps: 3000,
          clients_count: 7,
          balances: [],
        },
      ],
      total: 1,
    });

    const result = await loadPartnerPage(
      request as unknown as AdminApi,
      "RUB",
      DEFAULT_PARTNER_LIST_QUERY
    );

    expect(result.partners[0]).toMatchObject({
      userId: 34,
      name: "Alice Partner",
      handle: "@alice",
      avatarUrl: "/api/admin/users/34/avatar?v=1",
      clients: 7,
    });
  });

  it("shows partners with clients first by default", () => {
    expect(DEFAULT_PARTNER_LIST_QUERY.sort).toBe("clients_desc");
  });

  it("maps live Telegram identities for applications and withdrawals", () => {
    const partner = mapPartner(
      {
        partner_id: 12,
        user_id: 34,
        display_label: "Alice Partner",
        username: "alice",
        avatar_url: "/api/admin/users/34/avatar?v=1",
        status: "active",
        balances: [],
      },
      "RUB"
    );
    const application = mapApplication({
      application_id: 51,
      user_id: 35,
      display_label: "Bob Applicant",
      username: "bob",
      avatar_url: "/api/admin/users/35/avatar?v=2",
      status: "pending",
    });
    const withdrawal = mapWithdrawal(
      {
        withdrawal_id: 61,
        partner_id: 12,
        user_id: 34,
        display_label: "Alice Partner",
        username: "alice",
        avatar_url: "/api/admin/users/34/avatar?v=1",
        method_type: "bank_card",
        status: "requested",
      },
      new Map([[partner.id, partner]])
    );

    expect(application).toMatchObject({
      user: "Bob Applicant",
      handle: "@bob",
      avatarUrl: "/api/admin/users/35/avatar?v=2",
    });
    expect(withdrawal).toMatchObject({
      partner: "Alice Partner",
      handle: "@alice",
      avatarUrl: "/api/admin/users/34/avatar?v=1",
    });
  });

  it("supports a bounded top-partner page", async () => {
    const request = vi.fn().mockResolvedValue({ partners: [], total: 0 });

    await loadPartnerPage(request as unknown as AdminApi, "RUB", {
      ...DEFAULT_PARTNER_LIST_QUERY,
      sort: "earned_desc",
      limit: 3,
    });

    const query = new URLSearchParams(String(request.mock.calls[0][0]).split("?")[1]);
    expect(query.get("limit")).toBe("3");
    expect(query.get("sort")).toBe("earned_desc");
  });

  it("loads the complete partner chart history", async () => {
    const request = vi.fn().mockResolvedValue({ metrics: {}, series: [], currency_scale: 2 });

    await loadPartnerDashboard(request as unknown as AdminApi, "RUB");

    expect(String(request.mock.calls[0][0])).toContain("days=all");
  });

  it("maps linked client user ids in partner details", async () => {
    const request = vi.fn().mockResolvedValue({
      partner: { partner_id: 12, user_id: 34, display_label: "Partner", balances: [] },
      clients: [
        { public_client_id: "CL-1", client_user_id: 77, label: "Linked user" },
        { public_client_id: "CL-2", client_user_id: null, label: "Deleted user" },
      ],
    });

    const detail = await loadPartnerDetail(
      request as unknown as AdminApi,
      "12",
      "RUB",
      "/admin/partners/12"
    );

    expect(detail.clients.map((client) => client.userId)).toEqual([77, 0]);
  });

  it("rejects failed partner admin actions instead of reporting them as saved", () => {
    expect(() => requirePartnerAdminResponse({ ok: false, error: "reason_required" })).toThrow(
      "reason_required"
    );
  });
});
