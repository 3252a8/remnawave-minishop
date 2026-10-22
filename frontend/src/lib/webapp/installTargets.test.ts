import { describe, expect, it } from "vitest";
import {
  installAppId,
  installTargetFromSearch,
  installTargetSearch,
  resolveInstallTarget,
} from "./installTargets";
import type { InstallGuidePlatform } from "./types";

const platforms: InstallGuidePlatform[] = [
  {
    key: "ios",
    apps: [
      { id: "first", name: "First" },
      { id: "client-v2", name: "Client" },
    ],
  },
  { key: "android", apps: [{ id: "android-client", name: "Client" }] },
];

describe("install destinations", () => {
  it("uses stable application IDs when names or order change", () => {
    const target = installTargetFromSearch("?platform=ios&app=client-v2");
    expect(resolveInstallTarget(platforms, target, "android")).toEqual({
      platform: "ios",
      appIndex: 1,
    });
    expect(
      resolveInstallTarget(
        [{ key: "ios", apps: [{ id: "client-v2", name: "Renamed" }, { id: "first" }] }],
        target
      )
    ).toEqual({ platform: "ios", appIndex: 0 });
  });

  it("supports OS-only and app-only links and safely falls back for stale IDs", () => {
    expect(resolveInstallTarget(platforms, { platform: "ios" }, "android")).toEqual({
      platform: "ios",
      appIndex: 0,
    });
    expect(resolveInstallTarget(platforms, { app: "client-v2" }, "ios")).toEqual({
      platform: "ios",
      appIndex: 1,
    });
    expect(
      resolveInstallTarget(platforms, { platform: "missing", app: "missing" }, "android")
    ).toEqual({ platform: "android", appIndex: 0 });
    expect(resolveInstallTarget(platforms, { platform: "ios", app: "android-client" })).toEqual({
      platform: "ios",
      appIndex: 0,
    });
    expect(resolveInstallTarget([], {})).toEqual({ platform: "", appIndex: 0 });
  });

  it("normalizes old name-only catalogs without depending on position", () => {
    expect(installAppId({ name: "Clash Verge Rev" })).toBe("clash-verge-rev");
    expect(installAppId({ name: "??" })).toBe("app");
    expect(installAppId({ id: "Exact_ID", name: "Renamed" })).toBe("Exact_ID");
  });

  it("replaces destination parameters while preserving other query state", () => {
    expect(installTargetSearch("?lang=en&platform=ios&app=first", { platform: "android" })).toBe(
      "?lang=en&platform=android"
    );
    expect(installTargetSearch("?app=first", {})).toBe("");
    expect(installTargetFromSearch("?platform=%20ios%20&app=client-v2")).toEqual({
      platform: "ios",
      app: "client-v2",
    });
  });
});
