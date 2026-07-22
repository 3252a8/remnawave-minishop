import { describe, expect, it } from "vitest";

import {
  ADMIN_SECTION_GROUPS,
  ADMIN_SECTIONS,
  buildAdminSectionRouteAliases,
  defaultQueryForAdminSection,
  isAdminSectionVisible,
  mergeAdminSectionGroups,
  requiredFeatureForAdminSection,
  resolveAdminSectionId,
  type AdminSectionDescriptor,
} from "./registry";

function section(overrides: Partial<AdminSectionDescriptor>): AdminSectionDescriptor {
  return {
    id: "extension",
    group: "operations",
    order: 1,
    i18nKey: "extension",
    fallbackLabel: "Extension",
    titleI18nKey: "extension_title",
    fallbackTitle: "Extension",
    subtitleI18nKey: "extension_subtitle",
    fallbackSubtitle: "Extension section",
    icon: null,
    component: null,
    ...overrides,
  };
}

describe("admin extension feature metadata", () => {
  it("keeps legacy feature descriptors hidden when unavailable", () => {
    expect(isAdminSectionVisible(section({ feature: "reports" }), new Set())).toBe(false);
  });

  it("keeps a locked extension discoverable only when opted in", () => {
    const locked = section({ requiredFeature: "reports", visibleWhenLocked: true });

    expect(requiredFeatureForAdminSection(locked)).toBe("reports");
    expect(isAdminSectionVisible(locked, new Set())).toBe(true);
    expect(isAdminSectionVisible(section({ requiredFeature: "reports" }), new Set())).toBe(false);
  });

  it("shows required features after the entitlement becomes available", () => {
    expect(
      isAdminSectionVisible(section({ requiredFeature: "reports" }), new Set(["reports"]))
    ).toBe(true);
  });
});

describe("admin navigation groups", () => {
  it("orders neutral groups overview, operations, marketing, support, system", () => {
    const coreGroupIds = ADMIN_SECTION_GROUPS.map((group) => group.id);
    expect(coreGroupIds.slice(0, 5)).toEqual([
      "overview",
      "operations",
      "marketing",
      "support",
      "system",
    ]);
    // The legacy group id stays accepted for external extensions; it renders
    // only when an extension registers a section into it.
    expect(coreGroupIds).toContain("communication");
  });

  it("keeps only broadcast, promos, and ads in marketing and support/logs in support", () => {
    const byGroup = (groupId: string) =>
      ADMIN_SECTIONS.filter((section) => section.group === groupId)
        .sort((a, b) => a.order - b.order)
        .map((section) => section.id);
    expect(byGroup("marketing")).toEqual(["broadcast", "promos", "ads"]);
    expect(byGroup("support")).toEqual(["support", "logs"]);
    // Core itself no longer populates the legacy group.
    expect(byGroup("communication")).toEqual([]);
  });
});

describe("admin section route resolution", () => {
  it("resolves registered core section ids case-insensitively", () => {
    expect(resolveAdminSectionId("stats")).toBe("stats");
    expect(resolveAdminSectionId(" Users ")).toBe("users");
  });

  it("returns an empty id for slugs unknown to the registry", () => {
    expect(resolveAdminSectionId("definitely-unknown")).toBe("");
    expect(resolveAdminSectionId("")).toBe("");
    expect(resolveAdminSectionId(null)).toBe("");
  });

  it("canonicalizes registered route aliases without shadowing section ids", () => {
    const aliases = buildAdminSectionRouteAliases([
      section({ id: "combined", routeAliases: ["legacy-a", "Combined", "stats"] }),
      section({ id: "stats" }),
      section({ id: "other", routeAliases: ["legacy-a", "legacy-b"] }),
    ]);

    expect(aliases.get("legacy-a")).toBe("combined");
    expect(aliases.get("legacy-b")).toBe("other");
    // A registered section id can never be redirected elsewhere.
    expect(aliases.has("stats")).toBe(false);
    expect(aliases.has("combined")).toBe(false);
  });

  it("selects the first route default whose neutral feature requirement is met", () => {
    const descriptor = section({
      routeDefaults: [
        { requiredFeature: "extension.leads", query: { tab: "leads" } },
        { query: { tab: "business" } },
      ],
    });

    expect(defaultQueryForAdminSection(descriptor, new Set(["extension.leads"]))).toEqual({
      tab: "leads",
    });
    expect(defaultQueryForAdminSection(descriptor, new Set())).toEqual({ tab: "business" });
  });
});

describe("admin extension section groups", () => {
  it("adds and deterministically orders extension groups", () => {
    expect(
      mergeAdminSectionGroups(
        [{ id: "core", order: 20, i18nKey: "core", fallbackLabel: "Core" }],
        [{ id: "reports", order: 10, i18nKey: "reports", fallbackLabel: "Reports" }]
      ).map((group) => group.id)
    ).toEqual(["reports", "core"]);
  });

  it("keeps the core descriptor when an extension reuses its id", () => {
    expect(
      mergeAdminSectionGroups(
        [{ id: "system", order: 40, i18nKey: "core_system", fallbackLabel: "System" }],
        [{ id: "system", order: 1, i18nKey: "extension_system", fallbackLabel: "Override" }]
      )
    ).toEqual([{ id: "system", order: 40, i18nKey: "core_system", fallbackLabel: "System" }]);
  });
});
