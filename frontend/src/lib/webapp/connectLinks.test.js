import { describe, expect, it } from "vitest";

import {
  activationConnectLink,
  canUseSubscriptionInstallGuides,
  connectLinkFromSubscription,
  trialConnectLink,
} from "./connectLinks.js";

describe("connect link helpers", () => {
  it("prefers connect_url over config_link", () => {
    expect(
      connectLinkFromSubscription({
        config_link: "https://example.test/config",
        connect_url: "https://example.test/connect",
      })
    ).toBe("https://example.test/connect");
  });

  it("falls back to config_link and trims blanks", () => {
    expect(connectLinkFromSubscription({ config_link: " https://example.test/config " })).toBe(
      "https://example.test/config"
    );
    expect(connectLinkFromSubscription({ connect_url: "" })).toBe("");
  });

  it("requires both enabled guides and an active subscription", () => {
    expect(
      canUseSubscriptionInstallGuides({
        installGuidesEnabled: true,
        subscription: { active: true },
      })
    ).toBe(true);
    expect(
      canUseSubscriptionInstallGuides({
        installGuidesEnabled: false,
        subscription: { active: true },
      })
    ).toBe(false);
    expect(
      canUseSubscriptionInstallGuides({
        settings: { subscription_guides_enabled: true },
        subscription: { active: false },
      })
    ).toBe(false);
  });

  it("uses trial links before subscription fallback for trial actions", () => {
    expect(
      trialConnectLink(
        { connect_url: "https://example.test/trial" },
        { connect_url: "https://example.test/subscription" }
      )
    ).toBe("https://example.test/trial");
  });

  it("uses subscription links before trial fallback for activation dialogs", () => {
    expect(
      activationConnectLink(
        { config_link: "https://example.test/subscription" },
        { connect_url: "https://example.test/trial" }
      )
    ).toBe("https://example.test/subscription");
  });
});
