import { describe, expect, it } from "vitest";

import {
  documentHref,
  documentSlugFromLocation,
  hasInformationDocumentRole,
  hasInformationPageMarkdown,
  informationPagePathFromLocation,
  publicInformationDocuments,
  settingsInformationDocuments,
  sidebarInformationDocumentGroups,
} from "./informationPages.js";

describe("informationPagePathFromLocation", () => {
  it("keeps arbitrary safe information page routes", () => {
    expect(informationPagePathFromLocation("/company/about")).toBe("/company/about");
    expect(informationPagePathFromLocation("/company/about_us")).toBe("/company/about_us");
    expect(informationPagePathFromLocation("/legal/terms/")).toBe("/legal/terms");
  });

  it("does not capture SPA routes or traversal-shaped paths", () => {
    for (const path of [
      "/home",
      "/login/password",
      "/legal",
      "/webapp-logo",
      "/api/pages/about",
      "/docs/about",
      "/extensions/sample/resources",
      "/about%2fsecret",
    ]) {
      expect(informationPagePathFromLocation(path)).toBeNull();
    }
  });
});

describe("documentSlugFromLocation", () => {
  it("recognizes direct paths and the legacy documents prefix", () => {
    expect(documentSlugFromLocation("/docs/privacy-policy/")).toBe("privacy-policy");
    expect(documentSlugFromLocation("/docs/api/reference/")).toBe("api/reference");
    expect(documentSlugFromLocation("/guides/install/ios/")).toBe("guides/install/ios");
    expect(documentHref("guides/install/ios")).toBe("/guides/install/ios");
    expect(documentHref("/guides/install/ios")).toBe("/guides/install/ios");
    expect(documentHref("api/reference")).toBe("/docs/api/reference");
    expect(documentHref("extensions/sample/resources")).toBe("/docs/extensions/sample/resources");
  });

  it("rejects reserved roots and traversal-shaped paths", () => {
    expect(documentSlugFromLocation("/api/documents/about")).toBeNull();
    expect(documentSlugFromLocation("/extensions/sample/resources")).toBeNull();
    expect(documentSlugFromLocation("/about%2fsecret")).toBeNull();
    expect(documentSlugFromLocation("/docs/About")).toBeNull();
    expect(documentSlugFromLocation("/guides//install")).toBeNull();
  });
});

describe("publicInformationDocuments", () => {
  const documents = publicInformationDocuments({
    documents: [
      {
        slug: "support",
        title: "Support",
        group_title: "Help",
        show_in_settings: true,
        show_in_sidebar: false,
        sort_order: 2,
      },
      {
        slug: "privacy",
        title: "Privacy",
        group_title: "Legal",
        show_in_settings: true,
        show_in_sidebar: true,
        sort_order: 1,
        role: "privacy_policy",
      },
      {
        slug: "terms",
        title: "Terms",
        group_title: "Legal",
        show_in_settings: false,
        show_in_sidebar: true,
        sort_order: 2,
      },
    ],
  });

  it("keeps only explicitly enabled settings documents", () => {
    expect(settingsInformationDocuments(documents).map((document) => document.slug)).toEqual([
      "privacy",
      "support",
    ]);
  });

  it("groups sidebar documents and preserves their configured order", () => {
    expect(sidebarInformationDocumentGroups(documents)).toEqual([
      {
        title: "Legal",
        documents: [
          expect.objectContaining({ slug: "privacy" }),
          expect.objectContaining({ slug: "terms" }),
        ],
      },
    ]);
  });

  it("recognizes native legal roles independently of the settings checkbox", () => {
    expect(hasInformationDocumentRole(documents, "privacy_policy")).toBe(true);
    expect(hasInformationDocumentRole(documents, "user_agreement")).toBe(false);
  });
});

describe("hasInformationPageMarkdown", () => {
  it("requires visible markdown content", () => {
    expect(hasInformationPageMarkdown("# Document")).toBe(true);
    expect(hasInformationPageMarkdown("  \n ")).toBe(false);
    expect(hasInformationPageMarkdown(null)).toBe(false);
  });
});
