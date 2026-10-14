import { describe, expect, it } from "vitest";
import ru from "../../../../locales/ru.json";
import en from "../../../../locales/en.json";
import { formatTemplate } from "./formatters.js";
import { paymentDescriptionDisplay, paymentPurchaseDisplay } from "../admin/paymentTable.js";
import { paymentHistoryStatus, paymentHistoryTranslate } from "./paymentHistory.js";
import { DATASET } from "./mockApi/dataset.js";
import { demoPaymentHistoryItems } from "./mockApi/paymentHistory.js";
import type { Translate } from "./types.js";

for (const [language, locale] of Object.entries({ ru, en })) {
  describe(`payment history user localization in ${language}`, () => {
    const userScope: Record<string, string> = Object.fromEntries(
      Object.entries(locale).filter(([key]) => key.startsWith("wa_"))
    );
    const t: Translate = (key, params) => {
      expect(userScope[key], `Missing user-scoped translation: ${key}`).toBeDefined();
      return formatTemplate(userScope[key], params);
    };

    it("localizes provider and purchase cells without administrator translations or fallbacks", () => {
      const at = paymentHistoryTranslate(t);
      expect(at("gifts_source_admin")).not.toContain("wa_");
      const purchases = paymentPurchaseDisplay(
        {
          purchases: [
            { kind: "traffic", amount: 150, unit: "gb", scope: "regular", mode: "limit" },
            { kind: "traffic", amount: 50, unit: "gb", scope: "premium", mode: "limit" },
            { kind: "traffic", amount: 25, unit: "gb", scope: "regular", mode: "topup" },
            { kind: "traffic", amount: 10, unit: "gb", scope: "premium", mode: "topup" },
            { kind: "hwid_devices", amount: 2, unit: "device", mode: "topup" },
            { kind: "other", amount: 1, unit: "unit", mode: "topup" },
          ],
        },
        at
      );
      expect(purchases).toHaveLength(6);
      expect(paymentDescriptionDisplay({ traffic_regular_gb: 25 }, at)).toContain("25");
      expect(paymentDescriptionDisplay({ traffic_premium_gb: 10 }, at)).toContain("10");
    });

    it("explains every history state through the real user locale", () => {
      const items = demoPaymentHistoryItems(Number(DATASET.currentUser?.user_id));
      for (const item of items) {
        const status = paymentHistoryStatus(item, t);
        expect(status.label).not.toContain("wa_");
        expect(status.hint).not.toContain("wa_");
      }
    });
  });
}
