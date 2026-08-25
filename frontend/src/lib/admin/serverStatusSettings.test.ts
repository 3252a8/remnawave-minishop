import { describe, expect, it } from "vitest";

import type { AdminSettingsSection } from "./settingsSections";
import { filterServerStatusSettings, isKumaUrlValid } from "./serverStatusSettings";

const fields = [
  "SERVER_STATUS_ENABLED",
  "SERVER_STATUS_SHOW_ON_HOME",
  "SERVER_STATUS_PROVIDER",
  "SERVER_STATUS_URL",
  "SERVER_STATUS_KUMA_URL",
  "SERVER_STATUS_KUMA_SLUG",
  "SERVER_STATUS_XRAY_CHECKER_URL",
  "SERVER_STATUS_CACHE_TTL_SECONDS",
  "SERVER_STATUS_STALE_TTL_SECONDS",
  "SERVER_STATUS_TIMEOUT_SECONDS",
].map((key) => ({ key, label: key, subsection: "server_status" }));
const sections = [{ id: "system", fields }] as AdminSettingsSection[];

describe("filterServerStatusSettings", () => {
  it.each([
    [
      "url",
      [
        "SERVER_STATUS_ENABLED",
        "SERVER_STATUS_SHOW_ON_HOME",
        "SERVER_STATUS_PROVIDER",
        "SERVER_STATUS_URL",
      ],
    ],
    [
      "uptime-kuma",
      [
        "SERVER_STATUS_ENABLED",
        "SERVER_STATUS_SHOW_ON_HOME",
        "SERVER_STATUS_PROVIDER",
        "SERVER_STATUS_KUMA_URL",
        "SERVER_STATUS_KUMA_SLUG",
        "SERVER_STATUS_CACHE_TTL_SECONDS",
        "SERVER_STATUS_STALE_TTL_SECONDS",
        "SERVER_STATUS_TIMEOUT_SECONDS",
      ],
    ],
    [
      "xray-checker",
      [
        "SERVER_STATUS_ENABLED",
        "SERVER_STATUS_SHOW_ON_HOME",
        "SERVER_STATUS_PROVIDER",
        "SERVER_STATUS_XRAY_CHECKER_URL",
        "SERVER_STATUS_CACHE_TTL_SECONDS",
        "SERVER_STATUS_STALE_TTL_SECONDS",
        "SERVER_STATUS_TIMEOUT_SECONDS",
      ],
    ],
  ])("uses the dirty %s provider for all visible fields", (provider, expected) => {
    const visible = filterServerStatusSettings(sections, {
      SERVER_STATUS_PROVIDER: { value: provider, deleted: false },
    });
    expect(visible[0].fields.map((field) => field.key)).toEqual(expected);
    expect(sections[0].fields).toHaveLength(10);
  });
});

describe("isKumaUrlValid", () => {
  it.each(["http://status.example.test", "https://status.example.test", "", "  "])(
    "accepts %j",
    (value) => {
      expect(isKumaUrlValid(value)).toBe(true);
    }
  );

  it.each(["status.example.test", "ftp://status.example.test"])("rejects %j", (value) => {
    expect(isKumaUrlValid(value)).toBe(false);
  });
});
