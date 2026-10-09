import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

for (const width of [1280, 390]) {
  for (const language of ["ru", "en"] as const) {
    test(`user logs distinguish plugin, bot and web actions at ${width}px in ${language}`, async ({
      page,
    }, testInfo) => {
      const copy = JSON.parse(readFileSync(`../locales/${language}.json`, "utf8"));
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((lang) => {
        localStorage.setItem("rw_minishop_demo_language", lang);
        type Api = (path: string, options?: RequestInit) => Promise<Record<string, unknown>>;
        type Bundle = { mount: (target: HTMLElement, props: { api: Api }) => unknown };
        let bundle: Bundle | undefined;
        Object.defineProperty(window, "SubscriptionWebAppAdmin", {
          configurable: true,
          get: () => bundle,
          set(value: Bundle) {
            const mount = value.mount;
            value.mount = (target, props) =>
              mount(target, {
                ...props,
                api: async (path, options) => {
                  if (path.startsWith("/admin/logs?")) {
                    const params = new URL(path, location.origin).searchParams;
                    const logs = [
                      "plugin:sample:sample.completed",
                      "command:/start",
                      "webapp:payment_create",
                    ].map((event_type, index) => ({
                      log_id: index + 1,
                      user_id: Number(params.get("user_id")),
                      event_type,
                      content: index ? "Existing action" : "Completed",
                      timestamp: "2026-10-10T00:00:00Z",
                      is_admin_event: false,
                      target_user_id: null,
                    }));
                    return { ok: true, logs, total: logs.length, page: 0, page_size: 20 };
                  }
                  return props.api(path, options);
                },
              });
            bundle = value;
          },
        });
      }, language);
      await page.goto(
        "/demo/runtime/admin/users/ms_100000000000400080000000000de418?theme_preview=dark"
      );
      const card = page.locator(".admin-user-detail-page");
      await card.getByRole("tab", { name: copy.admin_user_tab_logs, exact: true }).click();
      const logs = card.locator(".admin-user-logs-tab");
      const plugin = logs.locator("tbody tr").filter({ hasText: "plugin:sample:sample.completed" });
      await expect(plugin).toContainText(copy.admin_user_logs_plugin_event);
      await expect(plugin).toContainText("Completed");
      await expect(logs.locator("tbody tr")).toHaveCount(3);
      await expect(logs).toContainText("command:/start");
      await expect(logs).toContainText("webapp:payment_create");
      expect(
        await card.evaluate((element) => element.scrollWidth - element.clientWidth)
      ).toBeLessThanOrEqual(1);
      expect(errors).toEqual([]);
      await plugin.scrollIntoViewIfNeeded();
      await page.screenshot({
        path: testInfo.outputPath(`plugin-user-logs-${width}-${language}.png`),
      });
    });
  }
}
