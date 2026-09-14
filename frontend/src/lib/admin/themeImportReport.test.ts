import { describe, expect, it } from "vitest";

import { normalizeThemeImportFailure, themeImportRecommendations } from "./themeImportReport.js";

const at = (_key: string, _params?: Record<string, unknown>, fallback = "") => fallback;

describe("theme import failure reports", () => {
  it("keeps the operation code and actionable detail", () => {
    expect(
      normalizeThemeImportFailure({ error: "missing_css_file", detail: "ocean/style.css" })
    ).toEqual({ code: "missing_css_file", detail: "ocean/style.css" });
  });

  it("reads nested API errors", () => {
    expect(
      normalizeThemeImportFailure({ error: { code: "repository_ref_not_found", detail: "v2" } })
    ).toEqual({ code: "repository_ref_not_found", detail: "v2" });
  });

  it("returns source-specific repair guidance and a clean retry step", () => {
    const recommendations = themeImportRecommendations("repository_ref_not_found", at);

    expect(recommendations[0]).toContain("public HTTPS GitHub or GitLab repository");
    expect(recommendations[0]).toContain("branch, tag, commit");
    expect(recommendations[1]).toContain("start a new import");
  });
});
