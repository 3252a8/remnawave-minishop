import { expect, test } from "@playwright/test";

for (const [width, language] of [
  [1440, "en"],
  [390, "ru"],
] as const) {
  test(`birthday settings are discoverable and editable at ${width}px in ${language}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript((lang) => {
      localStorage.setItem("rw_minishop_demo_language", lang);
    }, language);
    await page.goto("/demo/runtime/admin/settings?theme_preview=dark");
    await page.getByRole("searchbox").fill(language === "ru" ? "день рождения" : "birthday");
    await page.getByRole("option").filter({ hasText: "BIRTHDAY_ACTIVATION_CAMPAIGN" }).click();
    await expect(page).toHaveURL(/\/admin\/promos/);
    const dialog = page.getByRole("dialog");
    const toggle = dialog.getByRole("checkbox", {
      name: /^(Send a birthday code|Отправлять код ко дню рождения)$/,
    });
    const validity = dialog.getByRole("spinbutton", {
      name: /^(Validity after issue, days|Срок действия после выпуска, дней)$/,
    });
    await expect(toggle).not.toBeChecked();
    await toggle.click();
    await validity.fill("13");
    const effect = dialog.getByRole("checkbox", { name: /^(Discount|Скидка)$/ });
    await effect.click();
    await dialog.getByRole("button", { name: /^(Save|Сохранить)$/ }).click();
    await expect(dialog).toBeHidden();
    const card = page.locator("#birthday-activation-settings");
    await card.getByRole("button").click();
    await expect(toggle).toBeChecked();
    await expect(validity).toHaveValue("13");
    await expect(effect).toBeChecked();
    await toggle.click();
    await dialog.getByRole("button", { name: /^(Save|Сохранить)$/ }).click();
    await expect(dialog).toBeHidden();
    await card.getByRole("button").click();
    await expect(toggle).not.toBeChecked();
    await expect(effect).toBeChecked();
  });
}
