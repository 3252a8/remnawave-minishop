import { expect, test, type Page } from "@playwright/test";

const digest = "a".repeat(64);
const moduleSource = `
export function mountView(view, target, props) {
  if (view === 'broken') throw new Error('fixture failure');
  target.textContent = view;
  target.dataset.testid = 'fixture-' + view;
  target.dataset.parent = props.context?.parent || props.context?.sectionId || '';
  return { target };
}
export function updateView(instance, props) { instance.target.dataset.language = props.language || props.currentLang; }
export function unmountView(instance) { window.fixtureUnmounts = (window.fixtureUnmounts || 0) + 1; instance.target.textContent = ''; }
`;

async function assertNoOverflow(page: Page) {
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ).toBeLessThanOrEqual(2);
}

test("customer subsections keep their parent, direct links and failed replacement fallback", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/demo/runtime/**", async (route) => {
    if (route.request().resourceType() !== "document") return route.continue();
    const response = await route.fetch();
    const body = (await response.text()).replace(
      "</head>",
      '<script id="webapp-config" type="application/json">{"title":"Test shop"}</script></head>'
    );
    await route.fulfill({ response, body });
  });
  const views = [
    {
      id: "tool",
      view: "tool",
      label: "Tool",
      target: "page",
      parent: "invite",
      navigation: "section",
    },
    {
      id: "resources",
      view: "resources",
      label: "Resources",
      target: "page",
      parent: "support",
      navigation: "section",
    },
    {
      id: "tool-card",
      view: "tool-card",
      label: "Tool card",
      target: "user.invite.cards",
      placement: "after",
    },
    {
      id: "codes",
      view: "broken",
      label: "Replacement",
      target: "user.invite.codes",
      placement: "replace",
    },
  ];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.startsWith("/api/extensions/assets/"))
      return route.fulfill({ contentType: "text/javascript", body: moduleSource });
    let response: Record<string, unknown> = { ok: true };
    if (path === "/api/auth/session")
      response = { ok: true, authenticated: true, csrf_token: "fixture-csrf" };
    if (path === "/api/me")
      response = {
        ok: true,
        user: { id: 42, language_code: "ru", is_admin: false },
        settings: { support_tickets_enabled: true, referral_program_enabled: false },
        subscription: { active: false },
        plans: [],
        payment_methods: [],
        referral: {},
      };
    if (path === "/api/extensions/runtime")
      response = {
        ok: true,
        generation: 1,
        plugins: [
          {
            id: "sample",
            digest,
            entry: `/api/extensions/assets/sample/${digest}/index.js`,
            views,
          },
        ],
      };
    if (path === "/api/support/tickets")
      response = { ok: true, tickets: [], total: 0, page: 0, pages: 1 };
    if (path === "/api/gifts") response = { ok: true, enabled: false, gifts: [] };
    await route.fulfill({ json: response });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/demo/runtime/invite");
  await expect(page.getByTestId("fixture-tool-card")).toBeVisible();
  expect(errors).toEqual([]);
  await expect(page.locator(".promo-heading")).toBeVisible();
  await expect(
    page.getByText("Раздел временно недоступен. Попробуйте позже.", { exact: true })
  ).toBeVisible();
  await page.getByRole("button", { name: "Tool", exact: true }).click();
  await expect(page).toHaveURL(/\/extensions\/sample\/tool$/);
  await expect(page.getByTestId("fixture-tool")).toBeVisible();
  await expect(
    page.locator(".bottom-nav button.active").filter({ hasText: "Бонусы" })
  ).toBeVisible();
  await page.getByRole("button", { name: "Назад в раздел" }).click();
  await expect(page).toHaveURL(/\/invite$/);
  await expect(page.getByTestId("fixture-tool-card")).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  const card = await page.getByTestId("fixture-tool-card").boundingBox();
  const navigation = await page.locator(".bottom-nav").boundingBox();
  expect(card && navigation && card.y + card.height <= navigation.y).toBe(true);
  await assertNoOverflow(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/demo/runtime/extensions/sample/resources");
  await expect(page.getByTestId("fixture-resources")).toBeVisible();
  await page.getByRole("button", { name: "Назад в раздел" }).click();
  await expect(page.getByRole("button", { name: "Resources", exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByTestId("fixture-resources")).toBeVisible();
  await assertNoOverflow(page);
  expect(errors).toEqual([]);
});

test("admin tab-only packages add cards and restore direct subsection links", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/admin/plugins/assets/**", (route) =>
    route.fulfill({ contentType: "text/javascript", body: moduleSource })
  );
  await page.addInitScript(
    ({ digest }) => {
      type Bundle = { registerRuntimeExtensions?: (plugins: unknown[]) => void };
      let bundle: Bundle | undefined;
      Object.defineProperty(window, "SubscriptionWebAppAdmin", {
        configurable: true,
        get: () => bundle,
        set(value: Bundle) {
          value.registerRuntimeExtensions?.([
            {
              id: "sample",
              digest,
              entry: `/api/admin/plugins/assets/sample/${digest}/index.js`,
              section_tabs: [
                {
                  id: "resources",
                  view: "resources-editor",
                  sectionId: "support",
                  label: "Resources",
                  i18nKey: "fixture_resources",
                },
              ],
              slots: [
                {
                  id: "summary",
                  view: "help-summary",
                  label: "Help summary",
                  target: "admin.support.content",
                  placement: "before",
                },
              ],
            },
          ]);
          bundle = value;
        },
      });
    },
    { digest }
  );
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(
    "/demo/runtime/admin/support?extensionTab=sample%3Aresources&fixtureFilter=open#details"
  );
  await expect(page.getByTestId("fixture-resources-editor")).toBeVisible();
  await page.getByRole("tab", { name: "Поддержка", exact: true }).click();
  await expect(page.getByTestId("fixture-help-summary")).toBeVisible();
  await expect(page).not.toHaveURL(/extensionTab=/);
  await expect(page).toHaveURL(/fixtureFilter=open#details$/);
  await page.goBack();
  await expect(page.getByTestId("fixture-resources-editor")).toBeVisible();
  await page.locator('[data-admin-section="users"]').click();
  await expect(page).toHaveURL(/\/admin\/users\?/);
  await expect(page).not.toHaveURL(/extensionTab=/);
  await page.goBack();
  await expect(page.getByTestId("fixture-resources-editor")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("tab", { name: "Поддержка", exact: true }).click();
  await expect(page.getByTestId("fixture-help-summary")).toBeVisible();
  await assertNoOverflow(page);
  expect(errors).toEqual([]);
});
