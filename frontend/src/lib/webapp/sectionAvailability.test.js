import { describe, expect, it } from "vitest";

import { activeTabForWebappSection, resolveAvailableWebappSection } from "./sectionAvailability.js";

describe("section availability", () => {
  it("keeps available sections unchanged", () => {
    expect(
      resolveAvailableWebappSection({
        devicesEnabled: true,
        installGuidesAvailable: true,
        isAdmin: true,
        section: "devices",
        supportEnabled: true,
      })
    ).toBe("devices");
  });

  it("redirects unavailable guarded sections", () => {
    expect(resolveAvailableWebappSection({ isAdmin: false, section: "admin" })).toBe("settings");
    expect(resolveAvailableWebappSection({ devicesEnabled: false, section: "devices" })).toBe(
      "home"
    );
    expect(resolveAvailableWebappSection({ section: "support", supportEnabled: false })).toBe(
      "home"
    );
    expect(
      resolveAvailableWebappSection({
        installGuidesAvailable: false,
        section: "install",
      })
    ).toBe("home");
  });

  it("maps non-tab sections to their visible tab", () => {
    expect(activeTabForWebappSection("admin")).toBe("settings");
    expect(activeTabForWebappSection("install")).toBe("home");
    expect(activeTabForWebappSection("trial")).toBe("home");
    expect(activeTabForWebappSection("support")).toBe("support");
  });
});
