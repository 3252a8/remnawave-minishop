import { describe, expect, it } from "vitest";

import { DATASET } from "./dataset.js";
import { demoPartnerFixtureFacts } from "./partnerProgram.js";
import { partnerProgramDemoResponse } from "./partnerProgramResponse.js";

type CommissionFact = {
  client_user_id: number;
  partner_id: number;
  payment_id: number;
};

describe("partner program demo data", () => {
  const facts = demoPartnerFixtureFacts();
  const userIds = new Set((DATASET.adminUsers || []).map((user) => Number(user.user_id)));
  const payments = new Map(
    (DATASET.adminPayments || []).map((payment) => [Number(payment.payment_id), payment])
  );
  const partnerUserIds = facts.partner_user_ids as number[];
  const clientUserIds = facts.client_user_ids as number[];
  const commissions = facts.commissions as CommissionFact[];

  it("makes the logged-in demo user an active partner without inventing users", () => {
    expect(partnerUserIds[0]).toBe(Number(facts.current_user_id));
    expect(partnerUserIds.every((userId) => userIds.has(userId))).toBe(true);
    expect(clientUserIds.every((userId) => userIds.has(userId))).toBe(true);
    expect(new Set([...partnerUserIds, ...clientUserIds]).size).toBe(
      partnerUserIds.length + clientUserIds.length
    );
  });

  it("creates commissions only from successful payments owned by attributed clients", () => {
    expect(commissions.length).toBeGreaterThan(0);
    for (const commission of commissions) {
      const payment = payments.get(commission.payment_id);
      expect(payment, String(commission.payment_id)).toBeDefined();
      expect(Number(payment?.user_id), String(commission.payment_id)).toBe(
        commission.client_user_id
      );
      expect(String(payment?.status).toLowerCase(), String(commission.payment_id)).toBe(
        "succeeded"
      );
    }
  });

  it("serves populated partner views for the logged-in user and admin", () => {
    const overview = partnerProgramDemoResponse("/partner/overview", "/partner/overview", {});
    const clients = partnerProgramDemoResponse(
      "/partner/clients?currency=RUB&limit=200",
      "/partner/clients",
      {}
    );
    const dashboard = partnerProgramDemoResponse(
      "/admin/partners/overview?currency=RUB&days=all",
      "/admin/partners/overview",
      {}
    );

    expect((overview as Record<string, unknown>).profile).toMatchObject({
      user_id: facts.current_user_id,
      status: "active",
    });
    expect((clients as { clients: unknown[] }).clients.length).toBeGreaterThan(0);
    expect((dashboard as { metrics: { clients: number } }).metrics.clients).toBe(
      clientUserIds.length
    );
  });
});
