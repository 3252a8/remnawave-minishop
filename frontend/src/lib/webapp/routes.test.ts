import { describe, expect, it } from "vitest";

import { adminSectionFromPath, normalizeAdminSection } from "./routes";

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
