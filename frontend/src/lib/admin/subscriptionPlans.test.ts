import { describe, expect, it } from "vitest";
import {
  subscriptionPlanFilter,
  subscriptionPlanLabel,
  tariffFilterOptions,
  type SubscriptionPlan,
} from "./subscriptionPlans";

const at = (key: string, _params?: Record<string, unknown>, fallback?: string) => fallback || key;
const plan: SubscriptionPlan = {
  kind: "tariff",
  tariff_key: "Family_2026",
  tariff_names: { ru: "Семейный", en: "Family" },
  is_configured: true,
  is_enabled: true,
  is_active: true,
};

describe("subscription plan presentation", () => {
  it("uses the selected language and preserves the exact tariff identity", () => {
    expect(subscriptionPlanLabel(plan, "en-GB", at)).toBe("Family");
    expect(subscriptionPlanLabel(plan, "ru", at)).toBe("Семейный");
    expect(subscriptionPlanFilter(plan)).toBe("tariff:Family_2026");
    expect(subscriptionPlanLabel({ ...plan, tariff_names: {} }, "en", at)).toBe("Family_2026");
  });

  it("keeps trial, unassigned subscriptions and users who never subscribed distinct", () => {
    expect(subscriptionPlanLabel({ ...plan, kind: "trial" }, "en", at)).toBe("Trial");
    expect(subscriptionPlanFilter({ ...plan, kind: "trial" })).toBe("trial");
    expect(subscriptionPlanLabel({ ...plan, kind: "unassigned" }, "en", at)).toBe("No tariff");
    expect(subscriptionPlanLabel(null, "en", at)).toBe("No subscription");
  });

  it("keeps disabled tariffs selectable and retains a removed tariff from a deep link", () => {
    const options = tariffFilterOptions(
      [{ ...plan, tariff_key: "Family_2026", is_enabled: false }],
      "tariff:Removed/Plan",
      "en",
      at
    );
    expect(options).toContainEqual({ value: "tariff:Family_2026", label: "Family · Disabled" });
    expect(options).toContainEqual({
      value: "tariff:Removed/Plan",
      label: "Removed/Plan · Removed",
    });
  });

  it("disambiguates equal localized tariff names using their keys", () => {
    const options = tariffFilterOptions(
      [
        { ...plan, tariff_key: "monthly" },
        { ...plan, tariff_key: "annual" },
      ],
      "all",
      "en",
      at
    );
    expect(options).toContainEqual({ value: "tariff:monthly", label: "Family (monthly)" });
    expect(options).toContainEqual({ value: "tariff:annual", label: "Family (annual)" });
  });
});
