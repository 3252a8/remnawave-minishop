import { describe, expect, it, vi } from "vitest";

import type { AdminApi } from "../../admin/adminStores.js";
import {
  DEFAULT_PARTNER_LIST_QUERY,
  loadPartnerDashboard,
  loadPartnerLists,
  loadPartnerPage,
  mapApplication,
  mapPartner,
  mapWithdrawal,
  PARTNER_LIST_PAGE_SIZE,
  requirePartnerAdminResponse,
} from "./partnerProgramApi.js";

describe("partner program admin API", () => {
  it("starts withdrawals without waiting for partner rows and preserves the identity fallback", async () => {
    let releasePartners!: (value: object) => void;
    const partners = new Promise((resolve) => {
      releasePartners = resolve;
    });
    const api = vi.fn((path: string) => {
      if (path.startsWith("/admin/partners?")) return partners;
      if (path.startsWith("/admin/partner-withdrawals?"))
        return Promise.resolve({ withdrawals: [{ partner_id: 12, withdrawal_id: 7 }] });
      return Promise.resolve({ applications: [] });
    });
    const loading = loadPartnerLists(api as unknown as AdminApi, "RUB");
    expect(api).toHaveBeenCalledTimes(3);
    releasePartners({
      partners: [{ partner_id: 12, user_id: 34, display_label: "Alice", balances: [] }],
      total: 1,
    });
    const result = await loading;
    expect(result.withdrawals[0].partner).toBe("Alice");
    expect(result.withdrawals[0].handle).toBe("#34");
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

  it("rejects failed partner admin actions instead of reporting them as saved", () => {
    expect(() => requirePartnerAdminResponse({ ok: false, error: "reason_required" })).toThrow(
      "reason_required"
    );
  });
});
