import { expect, test, type Locator, type Page } from "@playwright/test";
import sharp from "sharp";
import jsQR from "jsqr";
import ru from "../../locales/ru.json";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const userRoute = "/demo/runtime/admin/users/ms_100000000000400080000000000de418";
const query = "?theme_preview=dark&issues_demo=1";
const devices = [
  ["desktop", { width: 1440, height: 1000 }],
  ["mobile", { width: 390, height: 844 }],
] as const;
async function snapshot(page: Page, name: string) {
  if (!process.env.ISSUE_REVIEW_DIR) return;
  await settleAnimations(page);
  await mkdir(process.env.ISSUE_REVIEW_DIR, { recursive: true });
  await page.screenshot({
    path: path.join(process.env.ISSUE_REVIEW_DIR, `after-${name}.png`),
    fullPage: !/(?:-qr|merge|tariff|referral-conditions)/.test(name),
  });
}
async function settleAnimations(page: Page) {
  await page.evaluate(async () => {
    await Promise.all(
      document
        .getAnimations()
        .filter(
          (animation) =>
            animation.playState === "running" &&
            Number.isFinite(animation.effect?.getComputedTiming().endTime ?? Infinity)
        )
        .map((animation) => animation.finished.catch(() => {}))
    );
  });
}

async function exposePromoHistory(page: Page) {
  await page.addInitScript(() => {
    type Api = (path: string, options?: RequestInit) => Promise<Record<string, unknown>>;
    type Bundle = { mount: (target: HTMLElement, props: { api: Api }) => unknown };
    let bundle: Bundle | undefined;
    Object.defineProperty(window, "SubscriptionWebAppAdmin", {
      configurable: true,
      get: () => bundle,
      set(value: Bundle) {
        const mount = value.mount;
        value.mount = (target, props) => {
          (
            window as unknown as {
              mergePromoHistory: () => Promise<Record<string, unknown>>;
            }
          ).mergePromoHistory = async () => {
            const response = await props.api("/admin/promos");
            const promos = response.promos as { id: number }[];
            return props.api(`/admin/promos/${promos[0].id}/activations`);
          };
          return mount(target, props);
        };
        bundle = value;
      },
    });
  });
}

async function promoHistory(page: Page) {
  return page.evaluate(() =>
    (
      window as unknown as { mergePromoHistory: () => Promise<Record<string, unknown>> }
    ).mergePromoHistory()
  );
}

for (const [device, viewport] of devices) {
  test(`merge ignores stale search and details, retries failures and prevents duplicate submission on ${device}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.addInitScript(() => {
      type Props = {
        api: (path: string, options?: RequestInit) => Promise<Record<string, unknown>>;
      };
      type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
      const controls = {
        contextMode: "error",
        searchFailed: false,
        posts: 0,
        releaseSearch: () => {},
        releaseContext: () => {},
        releasePost: () => {},
      };
      (window as unknown as { mergeReview: typeof controls }).mergeReview = controls;
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
                if (path.startsWith("/admin/users?")) {
                  const url = new URL(path, location.origin);
                  if (url.searchParams.get("q") === "failure" && !controls.searchFailed) {
                    controls.searchFailed = true;
                    return { ok: false, error: "unavailable" };
                  }
                  if (["failure", "slow"].includes(url.searchParams.get("q") || "")) {
                    if (url.searchParams.get("q") === "slow")
                      await new Promise<void>((resolve) => {
                        controls.releaseSearch = resolve;
                      });
                    url.searchParams.set("q", "alex.duplicate@example.com");
                    path = url.pathname + url.search;
                  }
                }
                if (path === "/admin/users/-987654/merge-context") {
                  if (controls.contextMode === "error") {
                    controls.contextMode = "defer";
                    return { ok: false, error: "unavailable" };
                  }
                  if (controls.contextMode === "defer") {
                    controls.contextMode = "normal";
                    await new Promise<void>((resolve) => {
                      controls.releaseContext = resolve;
                    });
                  }
                }
                if (path.endsWith("/merge") && options?.method === "POST") {
                  controls.posts += 1;
                  if (controls.posts === 1) return { ok: false, error: "account_merge_failed" };
                  await new Promise<void>((resolve) => {
                    controls.releasePost = resolve;
                  });
                }
                return props.api(path, options);
              },
            });
          bundle = value;
        },
      });
    });
    await page.goto(userRoute + query);
    const dialog = await openMerge(page);
    await searchMerge(page, "failure");
    await expect(dialog.locator(".picker-error")).toContainText(ru.admin_user_merge_search_failed);
    await expect(dialog.locator(".picker-user")).toHaveCount(0);
    await dialog.getByRole("button", { name: ru.admin_retry }).click();
    await expect(dialog.locator(".picker-user")).toHaveCount(1);
    const search = dialog.getByRole("searchbox");
    await search.fill("slow");
    await search.press("Enter");
    await expect(dialog.locator(".admin-user-picker")).toHaveAttribute("aria-busy", "true");
    await searchMerge(page, "alex.duplicate@example.com");
    await page.evaluate(() =>
      (
        window as unknown as { mergeReview: { releaseSearch: () => void } }
      ).mergeReview.releaseSearch()
    );
    await expect(search).toHaveValue("alex.duplicate@example.com");
    await chooseMerge(page, "Alex Duplicate account");
    await expect(dialog.getByRole("alert")).toContainText(ru.admin_user_merge_failed);
    await expect(dialog.locator(".merge-account")).toHaveCount(0);
    await dialog.getByRole("button", { name: ru.admin_retry }).click();
    await expect(dialog.getByRole("status")).toHaveText(ru.admin_user_merge_loading_details);
    await searchMerge(page, "review.4@example.com");
    await chooseMerge(page, "Review Candidate 4");
    await expect(dialog.locator('.merge-account[data-retained="false"]')).toContainText(
      "review.4@example.com"
    );
    await page.evaluate(() =>
      (
        window as unknown as { mergeReview: { releaseContext: () => void } }
      ).mergeReview.releaseContext()
    );
    await expect(dialog.locator('.merge-account[data-retained="false"]')).toContainText(
      "review.4@example.com"
    );
    await returnToMergeSearch(dialog);
    await searchMerge(page, "Alex");
    await chooseMerge(page, "Alex Duplicate account");
    const targetId = (await dialog
      .locator('.merge-account[data-retained="true"]')
      .getAttribute("data-user-id"))!;
    await dialog
      .getByRole("textbox", { name: ru.admin_user_merge_confirmation.replace("{id}", targetId) })
      .fill(targetId);
    await dialog.getByRole("button", { name: ru.admin_user_merge_confirm }).click();
    await expect(dialog.getByRole("alert")).toHaveText(ru.admin_user_merge_failed);
    await expect(dialog.getByRole("button", { name: ru.admin_user_merge_confirm })).toBeEnabled();
    await expectMergeActions(page, dialog, device, 3);
    await snapshot(page, `merge-transient-error-${device}`);
    await dialog.getByRole("button", { name: ru.admin_user_merge_confirm }).click();
    await expect(dialog.getByRole("button", { name: ru.admin_user_merge_busy })).toBeDisabled();
    await expect(
      dialog.getByRole("button", { name: ru.admin_user_merge_choose_another })
    ).toBeDisabled();
    expect(
      await dialog
        .locator(".dialog-footer button")
        .evaluateAll((nodes) => nodes.every((node) => (node as HTMLButtonElement).disabled))
    ).toBe(true);
    await expectMergeActions(page, dialog, device, 3);
    await snapshot(page, `merge-busy-${device}`);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeVisible();
    expect(
      await page.evaluate(
        () => (window as unknown as { mergeReview: { posts: number } }).mergeReview.posts
      )
    ).toBe(2);
    await page.evaluate(() =>
      (window as unknown as { mergeReview: { releasePost: () => void } }).mergeReview.releasePost()
    );
    await expect(dialog.getByRole("status")).toHaveText(ru.admin_user_merge_success);
  });
}
async function decodeQr(image: Buffer) {
  const { data, info } = await sharp(image)
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  return jsQR(new Uint8ClampedArray(data), info.width, info.height)?.data;
}
async function noOverflow(page: Page) {
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ).toBeLessThanOrEqual(2);
}
async function openMerge(page: Page) {
  await page.getByRole("tab", { name: ru.admin_user_tab_actions }).click();
  const trigger = page.locator('.admin-danger-zone [data-admin-action="request-user-merge"]');
  await trigger.click();
  await expect(page.locator(".admin-user-merge-dialog")).toBeVisible();
  await expect(page.locator(".admin-user-merge-dialog .dialog-close-button")).toBeFocused();
  return page.locator(".admin-user-merge-dialog");
}
async function searchMerge(page: Page, value: string) {
  const search = page.getByRole("searchbox", { name: ru.admin_user_merge_search });
  await search.fill(value);
  await search.press("Enter");
  await expect(page.locator(".admin-user-picker")).toHaveAttribute("aria-busy", "false");
}
async function chooseMerge(page: Page, name: string) {
  await page
    .getByRole("button", {
      name: ru.admin_user_merge_select_user.replace("{name}", name),
      exact: true,
    })
    .click();
}
async function returnToMergeSearch(dialog: Locator) {
  await dialog.getByRole("button", { name: ru.admin_user_merge_choose_another }).click();
  // Stage replacement restores focus on the next animation frame; typing must start after it.
  await expect(dialog.locator(".dialog-close-button")).toBeFocused();
  await expect(dialog.getByRole("searchbox")).toBeVisible();
}
async function expectMergeActions(page: Page, dialog: Locator, device: string, count: number) {
  const actions = dialog.locator(".merge-dialog-actions");
  const buttons = actions.getByRole("button");
  await expect(buttons).toHaveCount(count);
  await settleAnimations(page);
  const geometry = await actions.evaluate((node) => {
    const group = node.getBoundingClientRect();
    return {
      width: group.width,
      left: group.left,
      right: group.right,
      gap: parseFloat(getComputedStyle(node).gap),
      buttons: [...node.querySelectorAll("button")].map((button) => {
        const rect = button.getBoundingClientRect();
        return {
          x: rect.left,
          y: rect.top,
          right: rect.right,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
          libraryHeight: parseFloat(
            getComputedStyle(button).getPropertyValue("--ui-control-height")
          ),
          text: button.textContent?.trim(),
          danger: button.classList.contains("admin-btn-danger"),
        };
      }),
    };
  });
  for (const [index, button] of geometry.buttons.entries()) {
    expect(button.height).toBeCloseTo(button.libraryHeight, 1);
    expect(button.x).toBeGreaterThanOrEqual(geometry.left - 1);
    expect(button.right).toBeLessThanOrEqual(geometry.right + 1);
    expect(button.y).toBeGreaterThanOrEqual(0);
    expect(button.bottom).toBeLessThanOrEqual(page.viewportSize()!.height);
    if (device === "mobile") {
      expect(button.width).toBeCloseTo(geometry.width, 1);
      if (index) expect(button.y - geometry.buttons[index - 1].bottom).toBeCloseTo(geometry.gap, 1);
    } else if (index) {
      expect(button.y).toBeCloseTo(geometry.buttons[0].y, 1);
      expect(button.x - geometry.buttons[index - 1].right).toBeCloseTo(geometry.gap, 1);
    }
  }
  if (count === 3) {
    expect(geometry.buttons[0].text).toBe(ru.admin_cancel);
    expect(geometry.buttons[1].text).toBe(ru.admin_user_merge_choose_another);
    expect(geometry.buttons[2].danger).toBe(true);
  }
}

for (const [device, viewport] of devices) {
  test(`gift, referral and connection QR images export correctly on ${device}`, async ({
    page,
    context,
  }) => {
    await page.setViewportSize(viewport);
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto(`/demo/runtime/app/${query}&mock=checkout-addons&path=/invite`);
    const gift = page.locator(".gift-entry .copy-link-field").first();
    await expect(gift).toBeVisible();
    await expect(page.locator(".referral-tariff-dropdown")).toHaveCount(2);
    await expect(page.locator(".referral-tariff-dropdown").first()).toContainText(
      "Standard, Premium"
    );
    await expect(page.locator(".referral-tariff-dropdown").last()).toContainText("Family");
    await page.locator(".referral-tariff-dropdown").first().locator("summary").click();
    await page.locator(".referral-tariff-dropdown").last().locator("summary").click();
    await noOverflow(page);
    await snapshot(page, `invite-${device}`);
    await snapshot(page, `referral-terms-${device}`);
    await page
      .locator(".referral-tariff-dropdown")
      .first()
      .evaluate((node) => node.scrollIntoView({ block: "start", behavior: "instant" }));
    await snapshot(page, `referral-conditions-${device}`);
    const link = await gift.locator("input").inputValue();
    await gift.getByRole("button", { name: ru.wa_gift_qr_show }).click();
    const dialog = page.locator(".link-qr-dialog");
    await expect(dialog.locator(".link-qr-tile img")).toBeVisible();
    const image = await dialog.locator(".link-qr-tile img").getAttribute("src");
    expect(await decodeQr(Buffer.from(image!.split(",")[1], "base64"))).toBe(link);
    await snapshot(page, `gift-qr-${device}`);
    await dialog.getByRole("button", { name: ru.wa_qr_copy_image }).click();
    await expect(dialog.getByRole("status")).toHaveText(ru.wa_qr_image_copied);
    expect(
      await page.evaluate(async () =>
        (await navigator.clipboard.read()).some((item) => item.types.includes("image/png"))
      )
    ).toBe(true);
    await page.evaluate(() => {
      Object.defineProperty(navigator.clipboard, "write", {
        configurable: true,
        value: async () => {
          throw new DOMException("Denied", "NotAllowedError");
        },
      });
    });
    await dialog.getByRole("button", { name: ru.wa_qr_copy_image }).click();
    await expect(dialog.getByRole("status")).toHaveText(ru.wa_qr_copy_unavailable);
    const download = page.waitForEvent("download");
    await dialog.getByRole("button", { name: ru.wa_qr_download_png }).click();
    const file = await download;
    expect(file.suggestedFilename()).toBe("qr-code.png");
    const stream = await file.createReadStream();
    const chunks: Buffer[] = [];
    for await (const chunk of stream!) chunks.push(chunk);
    expect(await decodeQr(Buffer.concat(chunks))).toBe(link);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(gift.getByRole("button", { name: ru.wa_gift_qr_show })).toBeFocused();
    const referral = page.locator(".bonus-card .copy-link-field").first();
    const referralLink = await referral.locator("input").inputValue();
    await referral.getByRole("button", { name: /QR/ }).click();
    await expect(dialog.locator(".link-qr-tile img")).toBeVisible();
    const referralImage = await dialog.locator(".link-qr-tile img").getAttribute("src");
    expect(await decodeQr(Buffer.from(referralImage!.split(",")[1], "base64"))).toBe(referralLink);
    await snapshot(page, `referral-qr-${device}`);
    await page.keyboard.press("Escape");
    await page.goto(`/demo/runtime/app/${query}&mock=checkout-addons&path=/install`);
    const connection = page.locator(".install-subscription-card");
    await connection.scrollIntoViewIfNeeded();
    await expect(connection.locator(".install-qr-wrap img")).toBeVisible();
    await expect(connection.locator(".qr-image-actions")).toBeVisible();
    const actions = connection.locator(".qr-image-actions.is-icon-column button");
    await expect(actions).toHaveCount(2);
    for (const width of device === "mobile" ? [viewport.width, 320] : [viewport.width]) {
      await page.setViewportSize({ width, height: viewport.height });
      await connection.scrollIntoViewIfNeeded();
      await settleAnimations(page);
      const card = (await connection.boundingBox())!;
      const layout = (await page.locator(".install-layout").boundingBox())!;
      const qr = (await connection.locator(".install-qr-wrap").boundingBox())!;
      const copy = (await actions.first().boundingBox())!;
      const save = (await actions.last().boundingBox())!;
      const qrCenter = qr.x + qr.width / 2;
      const cardCenter = card.x + card.width / 2;
      const layoutCenter = layout.x + layout.width / 2;
      expect(Math.abs(qrCenter - cardCenter)).toBeLessThanOrEqual(1);
      expect(Math.abs(qrCenter - layoutCenter)).toBeLessThanOrEqual(1);
      expect(qr.width).toBe(qr.height);
      expect(qr.width).toBeLessThanOrEqual(204);
      expect(qr.width).toBeGreaterThanOrEqual(144);
      expect(copy.x).toBeGreaterThan(qr.x + qr.width);
      expect(Math.abs(copy.y - qr.y)).toBeLessThanOrEqual(1);
      expect(copy.width).toBe(36);
      expect(copy.height).toBe(36);
      expect(save.width).toBe(36);
      expect(save.height).toBe(36);
      expect(save.x).toBe(copy.x);
      expect(save.y).toBeGreaterThan(copy.y + copy.height);
      expect(save.x + save.width).toBeLessThanOrEqual(card.x + card.width);
      expect(await connection.evaluate((node) => node.scrollWidth - node.clientWidth)).toBe(0);
      await noOverflow(page);
      console.log(
        "Install QR geometry " +
          JSON.stringify({
            device,
            width,
            card,
            qr,
            qrCenter,
            cardCenter,
            layoutCenter,
            copy,
            save,
          })
      );
      await snapshot(page, `install-qr-${width === 320 ? "320" : device}`);
    }
    await page.setViewportSize(viewport);
    await expect(actions.first()).toHaveText("");
    await expect(
      page
        .locator(".install-subscription-card")
        .getByRole("button", { name: ru.wa_qr_download_png })
    ).toBeEnabled();
    await noOverflow(page);
    await page.goto(`/demo/runtime/home${query}&mock=no-subscription`);
    await page.locator('[data-webapp-action="open-payment"]:visible').first().click();
    const payment = page.locator(".dialog-card.webapp-payment-dialog");
    await expect(payment.locator(".tariff-row").first()).toBeVisible();
    await noOverflow(page);
    await snapshot(page, `tariffs-${device}`);
    await payment.locator(".tariff-row").first().click();
    await payment.locator(".payment-submit-button").first().click();
    await expect(payment.locator(".period-card").first()).toBeVisible();
    await snapshot(page, `tariff-selection-${device}`);
    await page.goto(`/demo/runtime/app/${query}&mock=checkout-addons&path=/invite&gift_demo=empty`);
    await expect(
      page.locator(".gift-entry").getByRole("button", { name: ru.wa_gift_qr_show })
    ).toHaveCount(0);
  });

  test(`administrator checks transfer direction and merges shared used promo history on ${device}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await exposePromoHistory(page);
    await page.goto(userRoute + query + "&merge_demo=shared-promo");
    await expect(
      page.locator('.admin-user-hero [data-admin-action="request-user-merge"]')
    ).toHaveCount(0);
    await page.getByRole("tab", { name: ru.admin_user_tab_actions }).click();
    const beforeHistory = await promoHistory(page);
    expect(beforeHistory.total).toBe(2);
    const beforeActivations = beforeHistory.activations as Record<string, unknown>[];
    expect(new Set(beforeActivations.map((item) => item.user_id)).size).toBe(2);
    expect(new Set(beforeActivations.map((item) => item.promo_id)).size).toBe(1);
    await page.locator(".admin-danger-zone").scrollIntoViewIfNeeded();
    const caption = page.locator(".admin-danger-zone-head small");
    await expect(caption).toHaveText(ru.admin_user_danger_zone_subtitle);
    expect(
      await caption.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(1);
    await snapshot(page, `danger-actions-${device}`);
    const dialog = await openMerge(page);
    await expect(dialog.locator(".picker-users li")).toHaveCount(25);
    await dialog
      .locator(".admin-pagination")
      .getByRole("button", { name: `${ru.admin_page_short} 2`, exact: true })
      .click();
    await expect(dialog.locator(".picker-users")).not.toContainText("Alex Duplicate account");
    await searchMerge(page, "no-such-account@example.com");
    await expect(dialog.getByRole("status")).toHaveText(ru.admin_user_merge_search_empty);
    await searchMerge(page, "ms_100000000000400080000000000de418");
    await expect(dialog.locator(".picker-user")).toHaveCount(1);
    await expect(dialog.locator(".picker-user")).toBeDisabled();
    await searchMerge(page, "-987654");
    await expect(dialog.locator(".picker-users li")).toHaveCount(1);
    await expectMergeActions(page, dialog, device, 1);
    await searchMerge(page, "alex.duplicate@example.com");
    await expect(dialog.locator(".picker-users li")).toHaveCount(1);
    await snapshot(page, `merge-search-${device}`);
    await chooseMerge(page, "Alex Duplicate account");
    await expect(dialog.locator(".merge-account")).toHaveCount(2);
    const targetId = (await dialog
      .locator('.merge-account[data-retained="true"]')
      .getAttribute("data-user-id"))!;
    await expect(dialog.locator(".merge-account").first()).toContainText(
      "alex.duplicate@example.com"
    );
    await expect(dialog.locator(".merge-account").first()).toContainText("google");
    await expect(dialog.locator(".merge-account").first()).toContainText("125.00 RUB");
    await expect(dialog.locator(".merge-account").first()).toContainText(
      ru.admin_user_merge_passkeys.replace("{count}", "1")
    );
    await expectMergeActions(page, dialog, device, 3);
    await snapshot(page, `merge-cards-${device}`);
    const submit = dialog.getByRole("button", { name: ru.admin_user_merge_confirm });
    await expect(submit).toBeDisabled();
    const confirmation = dialog.getByRole("textbox", {
      name: ru.admin_user_merge_confirmation.replace("{id}", targetId),
    });
    await confirmation.fill("wrong");
    await expect(submit).toBeDisabled();
    await confirmation.fill(targetId);
    await expect(submit).toBeEnabled();
    await expectMergeActions(page, dialog, device, 3);
    await noOverflow(page);
    const promoEffect = dialog.getByText(ru.admin_user_merge_effect_promos, { exact: true });
    await promoEffect.scrollIntoViewIfNeeded();
    await expect(promoEffect).toBeInViewport();
    await snapshot(page, `merge-shared-promo-confirm-${device}`);
    await snapshot(page, `merge-confirm-${device}`);
    await snapshot(page, `merge-${device}`);
    await returnToMergeSearch(dialog);
    await expect(dialog.getByRole("searchbox")).toHaveValue("alex.duplicate@example.com");
    await chooseMerge(page, "Alex Duplicate account");
    await expect(confirmation).toHaveValue("");
    await confirmation.fill(targetId);
    await submit.click();
    await expect(dialog.getByRole("status")).toHaveText(ru.admin_user_merge_success);
    await expectMergeActions(page, dialog, device, 1);
    await expect(dialog.locator(".dialog-footer button")).toBeEnabled();
    await expect(dialog.locator(".dialog-close-button")).toBeFocused();
    await snapshot(page, `merge-success-${device}`);
    await snapshot(page, `merge-shared-promo-${device}`);
    const afterHistory = await promoHistory(page);
    expect(afterHistory.total).toBe(2);
    expect(afterHistory.revenue_summary).toEqual(beforeHistory.revenue_summary);
    const afterActivations = afterHistory.activations as Record<string, unknown>[];
    expect(afterActivations.map((item) => item.user_id)).toEqual([
      Number(targetId),
      Number(targetId),
    ]);
    const historyFields = (rows: Record<string, unknown>[]) =>
      rows.map(({ activation_id, promo_id, activated_at, granted_days, payment_id }) => ({
        activation_id,
        promo_id,
        activated_at,
        granted_days,
        payment_id,
      }));
    expect(historyFields(afterActivations)).toEqual(historyFields(beforeActivations));
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(page.locator('[data-admin-action="request-user-merge"]')).toBeFocused();
    await page.goto(userRoute + query);
    await openMerge(page);
    await searchMerge(page, "910002");
    await dialog.locator(".picker-user").click();
    await expect(dialog.locator(".merge-account")).toHaveCount(2);
    await expect(dialog.getByRole("alert")).toHaveText(ru.admin_user_merge_telegram_conflict);
    await dialog.getByRole("alert").scrollIntoViewIfNeeded();
    await expect(submit).toBeDisabled();
    await expect(dialog.getByRole("textbox")).toHaveCount(0);
    await expectMergeActions(page, dialog, device, 3);
    await snapshot(page, `merge-conflict-${device}`);
    await snapshot(page, `merge-telegram-conflict-${device}`);
  });

  test(`merge blocks known restrictions and preserves a changed-state conflict on ${device}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto(userRoute + query + "&merge_demo=changed");
    const dialog = await openMerge(page);
    for (const [id, message, state] of [
      ["-987653", ru.admin_user_merge_protected, "protected"],
      ["-987652", ru.admin_user_merge_banned, "banned"],
      ["-987650", ru.admin_user_merge_provider_conflict, "provider-conflict"],
    ]) {
      await searchMerge(page, id);
      await dialog.locator(".picker-user").click();
      await expect(dialog.locator(".merge-comparison")).toContainText(id);
      await expect(dialog).toContainText(message);
      await expect(
        dialog.getByRole("button", { name: ru.admin_user_merge_confirm })
      ).toBeDisabled();
      await expect(dialog.getByRole("textbox")).toHaveCount(0);
      await expectMergeActions(page, dialog, device, 3);
      await snapshot(page, `merge-${state}-${device}`);
      await returnToMergeSearch(dialog);
    }
    await searchMerge(page, "-987651");
    await dialog.locator(".picker-user").click();
    await expect(dialog.getByRole("alert")).toContainText(ru.admin_user_merge_not_found);
    await expect(dialog.locator(".merge-account")).toHaveCount(0);
    await searchMerge(page, "Alex Duplicate account");
    await chooseMerge(page, "Alex Duplicate account");
    const targetId = (await dialog
      .locator('.merge-account[data-retained="true"]')
      .getAttribute("data-user-id"))!;
    await dialog
      .getByRole("textbox", { name: ru.admin_user_merge_confirmation.replace("{id}", targetId) })
      .fill(targetId);
    await dialog.getByRole("button", { name: ru.admin_user_merge_confirm }).click();
    await expect(dialog.getByRole("alert")).toHaveText(ru.admin_user_merge_protected);
    await expect(dialog.getByRole("alert")).toBeFocused();
    const submit = dialog.getByRole("button", { name: ru.admin_user_merge_confirm });
    await expect(submit).toBeDisabled();
    const confirmation = dialog.getByRole("textbox", {
      name: ru.admin_user_merge_confirmation.replace("{id}", targetId),
    });
    await confirmation.fill("wrong");
    await confirmation.fill(targetId);
    await expect(submit).toBeDisabled();
    await expect(dialog.getByRole("alert")).toHaveText(ru.admin_user_merge_protected);
    await dialog.getByRole("alert").scrollIntoViewIfNeeded();
    await expectMergeActions(page, dialog, device, 3);
    await snapshot(page, `merge-late-conflict-${device}`);
    if (device === "mobile") {
      await page.setViewportSize({ width: viewport.width, height: 640 });
      await expectMergeActions(page, dialog, device, 3);
      const warning = dialog.locator(".merge-effects > p");
      await warning.scrollIntoViewIfNeeded();
      await expect(warning).toBeInViewport();
      await dialog.getByRole("alert").scrollIntoViewIfNeeded();
      await expect(dialog.getByRole("alert")).toBeInViewport();
      await snapshot(page, "merge-late-conflict-mobile-short");
      await page.setViewportSize(viewport);
    }
    await returnToMergeSearch(dialog);
    await chooseMerge(page, "Alex Duplicate account");
    await expect(dialog.locator('.merge-account[data-retained="false"]')).toContainText(
      ru.admin_user_merge_protected
    );
    await expect(confirmation).toHaveCount(0);
    await expect(submit).toBeDisabled();
    await returnToMergeSearch(dialog);
    await expect(dialog.locator(".dialog-close-button")).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(page.locator('[data-admin-action="request-user-merge"]')).toBeFocused();
  });

  test(`plugin pages and shortcodes appear in message and menu editors on ${device}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    for (const [name, url] of [
      ["broadcast", "/demo/runtime/admin/broadcast"],
      ["user-message", userRoute],
      ["support", "/demo/runtime/admin/support/4101"],
    ]) {
      await page.goto(url + query);
      if (name === "user-message")
        await page.getByRole("tab", { name: ru.admin_user_tab_message }).click();
      const editor = page.locator(".message-buttons-editor").first();
      await editor
        .locator("..")
        .getByRole("button", { name: ru.admin_broadcast_button_add })
        .click();
      const row = editor.locator(".message-button-row").last();
      await row.locator(".message-button-kind").click();
      await page
        .getByRole("option", { name: ru.admin_broadcast_button_kind_webapp_section })
        .click();
      await row.locator(".message-button-target").click();
      await expect(page.getByRole("option", { name: ru.admin_demo_plugin_page })).toBeVisible();
      await noOverflow(page);
      await snapshot(page, `plugin-${name}-${device}`);
      await page.getByRole("option", { name: ru.admin_demo_plugin_page }).click();
      await expect(row.locator(".message-button-target")).toHaveText(
        new RegExp(ru.admin_demo_plugin_page)
      );
      await page.locator("[data-rt-shortcodes-toggle]").first().click();
      const shortcode = page
        .locator(".rt-menu-item")
        .filter({ hasText: "{sample-tools.plan_label}" });
      await expect(shortcode).toBeVisible();
      await shortcode.scrollIntoViewIfNeeded();
      if (name === "broadcast") await snapshot(page, `plugin-shortcodes-${device}`);
      await shortcode.click();
      await expect(
        page.locator(".rt-chip").filter({ hasText: "{sample-tools.plan_label}" })
      ).toBeVisible();
    }
    await page.goto("/demo/runtime/admin/settings/menu_buttons" + query);
    const menu = page.locator(".menu-buttons-editor");
    await menu.getByRole("button", { name: ru.admin_menu_buttons_add }).click();
    const row = menu.locator(".menu-buttons-row").last();
    await row.getByRole("button", { name: ru.admin_menu_buttons_target_type }).click();
    await page.getByRole("option", { name: ru.admin_menu_buttons_kind_webapp }).click();
    await row.getByRole("button", { name: ru.admin_menu_buttons_webapp_section }).click();
    await expect(page.getByRole("option", { name: ru.admin_demo_plugin_page })).toBeVisible();
    await snapshot(page, `plugin-menu-${device}`);
    await page.getByRole("option", { name: ru.admin_demo_plugin_page }).click();
    await noOverflow(page);
    expect(errors).toEqual([]);
  });
}
