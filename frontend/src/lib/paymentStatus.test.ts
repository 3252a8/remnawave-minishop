import { describe, expect, it } from "vitest";

import { paymentOutcome } from "./paymentStatus.js";
import { paymentStatusLabel, paymentStatusVariant } from "./admin/format.js";
import { createI18n } from "./webapp/i18n.js";
import ru from "../../../locales/ru.json";
import en from "../../../locales/en.json";

describe("paid payment outcomes", () => {
  it.each([false, true])("distinguishes fulfillment from provider payment (paid=%s)", (paid) => {
    expect(paymentOutcome({ status: "succeeded_pending_review", paid })).toBe("review");
    expect(paymentOutcome({ status: "succeeded_pending_finalization", paid })).toBe("finalizing");
    expect(paymentOutcome({ status: "succeeded", paid })).toBe("fulfilled");
  });

  it("keeps the existing success and failure response handling", () => {
    expect(paymentOutcome({ paid: true })).toBe("fulfilled");
    expect(paymentOutcome({ status: "pending" })).toBe("pending");
    expect(paymentOutcome({ status: "failed_provider" })).toBe("failed");
    expect(paymentOutcome({ status: "canceled" })).toBe("failed");
  });

  it.each([
    ["ru", "Оплачен · нужна проверка", "Оплачен · применяем покупку"],
    ["en", "Paid · needs review", "Paid · applying purchase"],
  ])("uses localized warning labels in %s", (language, review, finalizing) => {
    const { t } = createI18n({ messages: { ru, en }, defaultLang: language });
    const at = (key: string, params: Record<string, unknown> = {}, fallback = "") =>
      t(`admin_${key}`, params, fallback);

    expect(paymentStatusLabel("succeeded_pending_review", at)).toBe(review);
    expect(paymentStatusLabel("succeeded_pending_finalization", at)).toBe(finalizing);
    expect(t("wa_payment_pending_review")).not.toBe("wa_payment_pending_review");
    expect(t("wa_payment_pending_finalization")).not.toBe("wa_payment_pending_finalization");
    expect(paymentStatusVariant("succeeded_pending_review")).toBe("warning");
    expect(paymentStatusVariant("succeeded_pending_finalization")).toBe("warning");
    expect(paymentStatusVariant("succeeded")).toBe("success");
  });
});
