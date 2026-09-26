import { describe, expect, it } from "vitest";

import {
  adminPaymentsUserIdFromPath,
  adminPartnersDeepLinkFromPath,
  adminSectionFromPath,
  adminUserIdFromPath,
  normalizeAdminSection,
  sectionFromPath,
} from "./routes";

describe("admin user links", () => {
  const minishopId = `ms_${"a".repeat(32)}`;

  it("opens stable Minishop IDs in user and payment contexts", () => {
    expect(adminUserIdFromPath(`/admin/users/${minishopId}`)).toBe(minishopId);
    expect(adminPaymentsUserIdFromPath(`/admin/payments/users/${minishopId}`)).toBe(minishopId);
    expect(adminUserIdFromPath(`/demo/admin/users/${minishopId}`, "/demo")).toBe(minishopId);
  });

  it("keeps old numeric links and rejects malformed IDs", () => {
    expect(adminUserIdFromPath("/admin/users/-42")).toBe(-42);
    expect(adminPaymentsUserIdFromPath("/admin/payments/users/42")).toBe(42);
    expect(adminUserIdFromPath("/admin/users/ms_bad")).toBeNull();
  });
});

describe("sectionFromPath", () => {
  it("recognizes notification preferences as a Settings subsection", () => {
    expect(sectionFromPath("/settings/notifications")).toBe("notifications");
    expect(sectionFromPath("/demo/runtime/settings/notifications", "/demo/runtime")).toBe(
      "notifications"
    );
  });
});

describe("normalizeAdminSection", () => {
  it("keeps known core sections", () => {
    expect(normalizeAdminSection("users")).toBe("users");
    expect(normalizeAdminSection(" Stats ")).toBe("stats");
  });

  it("preserves well-formed extension slugs until the registry can validate them", () => {
    expect(normalizeAdminSection("pro-analytics")).toBe("pro-analytics");
    expect(normalizeAdminSection("ext_section2")).toBe("ext_section2");
  });

  it("falls back to the dashboard for malformed slugs", () => {
    expect(normalizeAdminSection("")).toBe("stats");
    expect(normalizeAdminSection(null)).toBe("stats");
    expect(normalizeAdminSection("-leading-dash")).toBe("stats");
    expect(normalizeAdminSection("with space")).toBe("stats");
    expect(normalizeAdminSection("path/../traversal")).toBe("stats");
  });
});

describe("adminSectionFromPath", () => {
  it("keeps extension deep links intact", () => {
    expect(adminSectionFromPath("/admin/pro-analytics")).toBe("pro-analytics");
    expect(adminSectionFromPath("/prefix/admin/pro-leads", "/prefix")).toBe("pro-leads");
  });

  it("normalizes unknown malformed segments and the bare admin path", () => {
    expect(adminSectionFromPath("/admin")).toBe("stats");
    expect(adminSectionFromPath("/admin/")).toBe("stats");
  });
});

describe("adminPartnersDeepLinkFromPath", () => {
  it("preserves partner-program list routes", () => {
    expect(adminPartnersDeepLinkFromPath("/admin/partners/partners")).toBe(
      "/admin/partners/partners"
    );
    expect(
      adminPartnersDeepLinkFromPath("/demo/runtime/admin/partners/applications/", "/demo/runtime")
    ).toBe("/admin/partners/applications");
    expect(adminPartnersDeepLinkFromPath("/admin/partners/withdrawals")).toBe(
      "/admin/partners/withdrawals"
    );
  });

  it("preserves supported partner-program detail routes", () => {
    expect(adminPartnersDeepLinkFromPath("/admin/partners/partner/PT-104")).toBe(
      "/admin/partners/partner/PT-104"
    );
    expect(
      adminPartnersDeepLinkFromPath(
        "/demo/runtime/admin/partners/applications/APP-1042",
        "/demo/runtime"
      )
    ).toBe("/admin/partners/applications/APP-1042");
    expect(adminPartnersDeepLinkFromPath("/admin/partners/withdrawals/WD-502/")).toBe(
      "/admin/partners/withdrawals/WD-502"
    );
  });

  it("rejects the base route, unknown detail kinds and nested identifiers", () => {
    expect(adminPartnersDeepLinkFromPath("/admin/partners")).toBe("");
    expect(adminPartnersDeepLinkFromPath("/admin/partners/unknown/PT-104")).toBe("");
    expect(adminPartnersDeepLinkFromPath("/admin/partners/partner/PT-104/more")).toBe("");
  });
});
