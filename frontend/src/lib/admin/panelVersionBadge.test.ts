import { describe, expect, it } from "vitest";

import { panelVersionBadgeState } from "./panelVersionBadge.js";
import type { PanelCompatibility } from "./stores/healthStore.svelte.js";

function compatibility(
  version: string | null,
  supportStatus = "unverified",
  certifiedVersions = ["7.4.2"]
): PanelCompatibility {
  return {
    version,
    generation: "test-generation",
    support_status: supportStatus,
    certified_versions: certifiedVersions,
    capabilities: [],
    observed_capabilities: {},
  };
}

describe("panelVersionBadgeState", () => {
  it("marks an exact certified release as verified", () => {
    expect(panelVersionBadgeState(compatibility("7.4.2", "current"))).toMatchObject({
      tone: "success",
      verification: "verified",
      displayVersion: "v7.4.2",
    });
  });

  it("warns for an unverified patch on a certified major.minor line", () => {
    expect(panelVersionBadgeState(compatibility("7.4.9"))).toMatchObject({
      tone: "warning",
      verification: "same_minor",
      versionLine: "7.4",
    });
  });

  it("marks versions outside certified minor lines as dangerous", () => {
    expect(panelVersionBadgeState(compatibility("7.5.0"))).toMatchObject({
      tone: "danger",
      verification: "unverified",
    });
  });

  it("keeps historical and unknown releases dangerous", () => {
    expect(panelVersionBadgeState(compatibility("7.4.1", "historical"))).toMatchObject({
      tone: "danger",
      verification: "historical",
    });
    expect(panelVersionBadgeState(compatibility(null, "unknown"))).toMatchObject({
      tone: "danger",
      verification: "unknown",
      displayVersion: "—",
    });
  });
});
