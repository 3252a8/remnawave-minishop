import { describe, expect, it } from "vitest";

import {
  isAdminSectionVisible,
  requiredFeatureForAdminSection,
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
