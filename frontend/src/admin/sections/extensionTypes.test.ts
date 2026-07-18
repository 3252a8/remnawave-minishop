import { describe, expect, it } from "vitest";

import { isFeatureBoundDescriptorVisible, requiredFeatureForDescriptor } from "./extensionTypes";

describe("feature-bound extension descriptors", () => {
  it("hides a user detail panel until its required feature is available", () => {
    const panel = { requiredFeature: "audience.timeline" };

    expect(requiredFeatureForDescriptor(panel)).toBe("audience.timeline");
    expect(isFeatureBoundDescriptorVisible(panel, new Set())).toBe(false);
    expect(isFeatureBoundDescriptorVisible(panel, new Set(["audience.timeline"]))).toBe(true);
  });

  it("keeps a locked panel discoverable when requested", () => {
    expect(
      isFeatureBoundDescriptorVisible(
        { requiredFeature: "audience.timeline", visibleWhenLocked: true },
        new Set()
      )
    ).toBe(true);
  });
});
