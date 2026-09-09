import { jsonBody } from "../demoMockRuntime.js";
import { defaultClone, type DemoRecord, type MockApiContext } from "./dataset.js";
import { partnerProgramFixtureRuntime as fixture } from "./partnerProgram.js";

export function partnerProgramDemoResponse(
  path: string,
  cleanPath: string,
  options: RequestInit,
  context: MockApiContext = {}
): unknown {
  const clone = context.clone || defaultClone;
  const method = String(options.method || "GET").toUpperCase();
  const activePartner = fixture.currentPartner();
  if (!activePartner) return undefined;

  if (cleanPath === "/partner/overview") {
    return clone({
      ok: true,
      program_enabled: true,
      withdrawals_enabled: true,
      balance_payment_enabled: true,
      encryption_available: true,
      application_message_max_length: 2000,
      application: null,
      profile: fixture.baseProfilePayload(activePartner),
      balances: [fixture.balancePayload(activePartner.partnerId)],
      links: fixture.linksFor(activePartner),
      withdrawal_methods: fixture.withdrawalMethods(),
    });
  }

  const webLists: Array<{ path: string; key: string; values: DemoRecord[] }> = [
    {
      path: "/partner/clients",
      key: "clients",
      values: fixture.clientFixtures
        .filter((item) => item.partnerId === activePartner.partnerId)
        .map(fixture.clientPayload),
    },
    {
      path: "/partner/commissions",
      key: "commissions",
      values: fixture.commissionFixtures
        .filter((item) => item.partnerId === activePartner.partnerId)
        .map(fixture.commissionPayload),
    },
    {
      path: "/partner/withdrawals",
      key: "withdrawals",
      values: fixture.withdrawalFixtures
        .filter((item) => item.partnerId === activePartner.partnerId)
        .map((item) => fixture.withdrawalPayload(item)),
    },
  ];
  const webList = webLists.find((item) => item.path === cleanPath && method === "GET");
  if (webList) {
    const page = fixture.paginatedPayload(webList.values, path);
    return clone({
      ok: true,
      [webList.key]: page.items,
      total: page.total,
      limit: page.limit,
      offset: page.offset,
    });
  }
  if (cleanPath === "/partner/withdrawals" && method === "POST") {
    const requested = fixture.withdrawalFixtures.find(
      (item) => item.partnerId === activePartner.partnerId && item.status === "requested"
    );
    return clone({
      ok: true,
      withdrawal: requested ? fixture.withdrawalPayload(requested) : null,
    });
  }
  const cancelMatch = cleanPath.match(/^\/partner\/withdrawals\/(\d+)\/cancel$/);
  if (cancelMatch && method === "POST") {
    const withdrawal = fixture.withdrawalFixtures.find(
      (item) =>
        item.withdrawalId === Number(cancelMatch[1]) && item.partnerId === activePartner.partnerId
    );
    return clone({
      ok: true,
      withdrawal: withdrawal
        ? { ...fixture.withdrawalPayload(withdrawal), status: "canceled" }
        : null,
    });
  }

  if (cleanPath === "/admin/partners/attention") {
    return {
      ok: true,
      pending_applications: fixture.applicationFixtures.filter((item) => item.status === "pending")
        .length,
      open_withdrawals: fixture.withdrawalFixtures.filter(
        (item) => item.status === "requested" || item.status === "processing"
      ).length,
    };
  }
  if (cleanPath === "/admin/partners/overview") return clone(fixture.adminOverview());
  if (cleanPath === "/admin/partners" && method === "GET") {
    return clone(fixture.partnerList(path));
  }
  if (cleanPath === "/admin/partner-applications" && method === "GET") {
    const page = fixture.paginatedPayload(fixture.applicationFixtures, path);
    return clone({
      ok: true,
      applications: page.items.map(fixture.applicationPayload),
      total: page.total,
      limit: page.limit,
      offset: page.offset,
    });
  }
  if (cleanPath === "/admin/partner-withdrawals" && method === "GET") {
    const page = fixture.paginatedPayload(fixture.withdrawalFixtures, path);
    return clone({
      ok: true,
      withdrawals: page.items.map((item) => fixture.withdrawalPayload(item, true)),
      total: page.total,
      limit: page.limit,
      offset: page.offset,
    });
  }
  if (cleanPath === "/admin/partners/referral-import") {
    return method === "POST"
      ? {
          ok: true,
          result: {
            imported: 0,
            existing: fixture.clientFixtures.length,
            conflicts: 0,
            partners_updated: 0,
          },
        }
      : {
          ok: true,
          preview: {
            found: fixture.clientFixtures.length,
            importable: 0,
            already_this_partner: fixture.clientFixtures.length,
            other_partner: 0,
            self_conflict: 0,
            historical_payments: fixture.commissionFixtures.length,
            partners: fixture.partnerFixtures.length,
          },
        };
  }

  const partnerDetailMatch = cleanPath.match(/^\/admin\/partners\/(\d+)$/);
  if (partnerDetailMatch && method === "GET") {
    const partner = fixture.partnersById.get(Number(partnerDetailMatch[1]));
    return partner
      ? clone(fixture.partnerDetail(partner))
      : { ok: false, error: "partner_not_found" };
  }
  const referralImportMatch = cleanPath.match(/^\/admin\/partners\/(\d+)\/referral-import$/);
  if (referralImportMatch) {
    const partnerId = Number(referralImportMatch[1]);
    const clients = fixture.clientFixtures.filter((item) => item.partnerId === partnerId);
    const commissions = fixture.commissionFixtures.filter((item) => item.partnerId === partnerId);
    return method === "POST"
      ? { ok: true, result: { imported: 0, existing: clients.length, conflicts: 0 } }
      : {
          ok: true,
          preview: {
            found: clients.length,
            importable: 0,
            already_this_partner: clients.length,
            other_partner: 0,
            self_conflict: 0,
            historical_payments: commissions.length,
          },
        };
  }
  const applicationMatch = cleanPath.match(
    /^\/admin\/partner-applications\/(\d+)(?:\/(approve|reject|reopen))?$/
  );
  if (applicationMatch) {
    const application = fixture.applicationFixtures.find(
      (item) => item.applicationId === Number(applicationMatch[1])
    );
    if (!application) return { ok: false, error: "application_not_found" };
    const transition = applicationMatch[2];
    const status =
      transition === "approve"
        ? "approved"
        : transition === "reject"
          ? "rejected"
          : application.status;
    return clone({
      ok: true,
      application: fixture.applicationPayload({ ...application, status }),
    });
  }
  const withdrawalMatch = cleanPath.match(
    /^\/admin\/partner-withdrawals\/(\d+)(?:\/(processing|paid|reject|fail|reveal))?$/
  );
  if (withdrawalMatch) {
    const withdrawal = fixture.withdrawalFixtures.find(
      (item) => item.withdrawalId === Number(withdrawalMatch[1])
    );
    if (!withdrawal) return { ok: false, error: "withdrawal_not_found" };
    if (withdrawalMatch[2] === "reveal") {
      return { ok: true, requisites: { value: withdrawal.masked } };
    }
    const status =
      withdrawalMatch[2] === "reject"
        ? "rejected"
        : withdrawalMatch[2] === "fail"
          ? "failed"
          : withdrawalMatch[2] || withdrawal.status;
    return clone({
      ok: true,
      withdrawal: { ...fixture.withdrawalPayload(withdrawal, true), status },
    });
  }
  const partnerActionMatch = cleanPath.match(
    /^\/admin\/partners\/(\d+)\/(commission-rate|balance-adjustments|pause|resume|close|link\/rotate)$/
  );
  if (partnerActionMatch && method === "POST") {
    const partner = fixture.partnersById.get(Number(partnerActionMatch[1]));
    if (!partner) return { ok: false, error: "partner_not_found" };
    const body = jsonBody(options);
    const status =
      partnerActionMatch[2] === "pause"
        ? "paused"
        : partnerActionMatch[2] === "resume"
          ? "active"
          : partnerActionMatch[2] === "close"
            ? "closed"
            : partner.status;
    const commissionBps =
      partnerActionMatch[2] === "commission-rate"
        ? Number(body.commission_bps || partner.commissionBps)
        : partner.commissionBps;
    return clone({
      ok: true,
      partner: fixture.adminProfilePayload({ ...partner, status, commissionBps }),
    });
  }
  return undefined;
}
