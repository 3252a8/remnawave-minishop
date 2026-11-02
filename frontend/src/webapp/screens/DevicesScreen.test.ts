import { readFileSync } from "node:fs";
import { render } from "svelte/server";
import { describe, expect, it } from "vitest";

import DevicesScreen from "./DevicesScreen.svelte";

const locale: Record<string, string> = JSON.parse(
  readFileSync(new URL("../../../../locales/en.json", import.meta.url), "utf8")
);
const t = (key: string) => locale[key] || key;

describe("DevicesScreen progress semantics", () => {
  it("renders the Lucide router icon and localized type after a device rename", () => {
    const html = render(DevicesScreen, {
      props: {
        devicesData: {
          devices: [
            {
              index: 1,
              token: "router",
              display_name: "My phone",
              default_name: "Keenetic Giga",
              custom_name: "My phone",
              device_model: "Keenetic Giga",
              device_type: "router",
              router_platform: "keenetic",
              platform: "Linux",
              platform_label: "Linux",
              os_version: "",
              user_agent: "",
              created_at: null,
              created_at_text: "",
              last_connected_at: null,
              last_connected_at_text: "",
              hwid_short: "",
              can_disconnect: true,
            },
          ],
        },
        devicesLoaded: true,
        subscription: { active: true },
        t,
      },
    }).body;
    expect(html).toContain('data-device-shape="router"');
    expect(html).toContain("lucide-router");
    expect(html).toContain("Keenetic Giga · Router · Linux");
    expect(html).toContain('data-webapp-action="open-device-disconnect"');
    expect(html).toContain('data-webapp-action="open-device-rename"');
  });

  it.each([
    { current: 199, max: 200, state: "available", percent: 100 },
    { current: 200, max: 200, state: "reached", percent: 100 },
    { current: 201, max: 200, state: "reached", percent: 100 },
    { current: 3, max: 0, state: "unlimited", percent: undefined },
    { current: 3, max: null, state: "pending", percent: undefined },
  ])("renders $state for $current devices with limit $max", ({ current, max, state, percent }) => {
    const html = render(DevicesScreen, {
      props: {
        devicesData: { current_devices: current, max_devices: max, devices: [] },
        devicesLoaded: true,
        subscription: { active: true },
        t,
      },
    }).body;
    const progress = html.match(/<div[^>]*class="progress devices-progress"[^>]*>/)?.[0];
    expect(progress).toContain(`data-state="${state}"`);
    expect(progress).toContain(`aria-valuetext="${locale[`wa_devices_progress_${state}`]}"`);
    if (percent === undefined) expect(progress).not.toContain("aria-valuenow");
    else expect(progress).toContain(`aria-valuenow="${percent}"`);
    expect(html).toContain('role="status"');
    expect(html).toContain(locale[`wa_devices_progress_${state}`]);
  });

  it("stays pending while the first device load has not completed", () => {
    const html = render(DevicesScreen, {
      props: {
        devicesData: { current_devices: 3, max_devices: 3, devices: [] },
        devicesLoaded: false,
        devicesBusy: true,
        subscription: { active: true },
        t,
      },
    }).body;
    expect(html).toContain('data-state="pending"');
    expect(html).not.toContain('data-state="reached"');
    expect(html).not.toContain("aria-valuenow");
    expect(html).toContain("width: 0%");
  });
});
