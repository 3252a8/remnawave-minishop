import { describe, expect, it } from "vitest";

import {
  DEV_DOCUMENTATION_URL,
  documentationBaseUrlForVersion,
  RELEASE_DOCUMENTATION_URL,
} from "./documentationUrl.js";

describe("documentationBaseUrlForVersion", () => {
  it.each(["v1.2.3", "1.2.3", "v1.2.3+gabcdef1"])(
    "uses release documentation for stable build %s",
    (version) => {
      expect(documentationBaseUrlForVersion(version)).toBe(RELEASE_DOCUMENTATION_URL);
    }
  );

  it.each([
    "dev+local",
    "dev+unknown",
    "v1.2.3-dev+gabcdef1",
    "v1.2.3-feature-login+gabcdef1",
    "v1.2.3-rc1",
    "",
  ])("uses dev documentation for non-release build %s", (version) => {
    expect(documentationBaseUrlForVersion(version)).toBe(DEV_DOCUMENTATION_URL);
  });
});
