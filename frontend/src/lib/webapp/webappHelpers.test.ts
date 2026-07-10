import { describe, expect, it } from "vitest";

import { invalidateWebappTariffOptionCaches } from "./billingOptionCache.js";
import {
  formatCompactNumber,
  formatFraction,
  formatMoney,
  formatTemplate,
  formatTrafficBytes,
  formatTrafficGb,
  normalizedEmail,
  roundToHalf,
  telegramName,
} from "./formatters.js";
import { ruFractionAware, ruPlural, unitPluralBucket } from "./plurals.js";
import {
  activeSubscriptionTermLabel,
  isForeverSubscription,
  premiumNextResetLabel,
  premiumServerLabels,
  premiumTrafficLeftLabel,
  trafficLabel,
  trafficNextResetLabel,
  trafficPercent,
  trafficResetLabel,
  trafficResetScheduled,
} from "./traffic.js";

describe("webapp formatters", () => {
  it("formats template, money, traffic and profile display values", () => {
    expect(formatTemplate("Hello {name}, {missing}", { name: "Ann" })).toBe("Hello Ann, {missing}");
    expect(formatMoney(12.5, "USD")).toBe("12.50 USD");
    expect(formatTrafficGb(12.5)).toBe("12.5 GB");
    expect(formatTrafficBytes(3 * 1073741824)).toBe("3 GB");
    expect(formatCompactNumber(12.5)).toBe("12.5");
    expect(roundToHalf(1.24)).toBe(1);
    expect(roundToHalf(1.26)).toBe(1.5);
    expect(formatFraction(2.5)).toBe("2.5");
    expect(normalizedEmail(" User@Example.COM ")).toBe("user@example.com");
    expect(telegramName({ username: "ann" }, "fallback")).toBe("@ann");
    expect(telegramName({ first_name: "Ann", last_name: "Lee" }, "fallback")).toBe("Ann Lee");
  });
});

describe("webapp plurals", () => {
  it("selects Russian and fallback plural buckets", () => {
    expect(ruPlural(1, "one", "few", "many")).toBe("one");
    expect(ruPlural(2, "one", "few", "many")).toBe("few");
    expect(ruPlural(5, "one", "few", "many")).toBe("many");
    expect(ruPlural(11, "one", "few", "many")).toBe("many");
    expect(ruPlural(21, "one", "few", "many")).toBe("one");
    expect(ruFractionAware(1.5, "one", "few", "many")).toBe("few");
    expect(unitPluralBucket(2.5, "ru")).toBe("few");
    expect(unitPluralBucket(2, "en")).toBe("many");
  });
});

describe("webapp traffic helpers", () => {
  const t = (key: string, params: Record<string, unknown> = {}) =>
    `${key}:${JSON.stringify(params)}`;
  const termUnitLabel = (value: unknown, unit: unknown) => `${unit}:${value}`;

  it("clamps regular traffic percent and builds labels", () => {
    expect(trafficPercent({ traffic_used_bytes: 150, traffic_limit_bytes: 100 })).toBe(100);
    expect(trafficPercent({ traffic_used_bytes: -10, traffic_limit_bytes: 100 })).toBe(0);
    expect(trafficPercent({ traffic_used_bytes: 10, traffic_limit_bytes: 0 })).toBe(100);
    expect(
      trafficLabel({ traffic_used: "2 GB", traffic_limit: "5 GB", traffic_limit_bytes: 5 }, t)
    ).toBe('wa_traffic_of:{"used":"2 GB","limit":"5 GB"}');
    expect(trafficLabel({ traffic_limit_bytes: 0 }, t)).toBe("wa_unlimited_traffic:{}");
  });

  it("maps traffic reset strategies to translation keys", () => {
    expect(trafficResetLabel({ traffic_limit_strategy: "MONTHLY" }, t)).toBe(
      "wa_traffic_reset_monthly:{}"
    );
    expect(trafficResetLabel({ traffic_limit_strategy: "NO_RESET" }, t)).toBe(
      "wa_traffic_reset_none:{}"
    );
    expect(trafficResetLabel({ traffic_limit_strategy: "CUSTOM" }, t)).toBe(
      "wa_traffic_reset_policy:{}"
    );
    expect(trafficResetScheduled({ traffic_limit_strategy: "MONTH_ROLLING" })).toBe(true);
    expect(trafficResetScheduled({ traffic_limit_strategy: "NO_RESET" })).toBe(false);
    expect(trafficNextResetLabel({ traffic_next_reset_text: "05.07.2026" }, t)).toBe("05.07.2026");
    expect(premiumNextResetLabel({ premium_next_reset_text: "" }, t)).toBe(
      "wa_traffic_next_reset_none:{}"
    );
  });

  it("formats premium traffic and subscription terms", () => {
    expect(
      premiumTrafficLeftLabel({
        premium_limit_bytes: 5 * 1073741824,
        premium_used_bytes: 2 * 1073741824,
      })
    ).toBe("3 GB");
    expect(premiumServerLabels({ premium_node_labels: [" One ", "", "Two"] })).toEqual([
      "One",
      "Two",
    ]);
    expect(isForeverSubscription({ end_date_text: "2099-12-31" })).toBe(true);
    expect(activeSubscriptionTermLabel({ days_left: 45 }, { t, termUnitLabel })).toBe(
      'wa_sub_term_value_unit:{"value":"1.5","unit":"month:1.5"}'
    );
  });
});

describe("billing option cache", () => {
  it("invalidates cached option payloads while preserving other state", () => {
    const billingStore = {
      value: {
        topupOptions: { ok: true },
        deviceTopupOptions: { ok: true },
        changeOptions: { ok: true },
        selectedMethod: "card",
      } as Record<string, unknown>,
      update(fn: (value: Record<string, unknown>) => Record<string, unknown>) {
        this.value = fn(this.value);
      },
    };

    invalidateWebappTariffOptionCaches(
      billingStore as unknown as Parameters<typeof invalidateWebappTariffOptionCaches>[0]
    );

    expect(billingStore.value).toEqual({
      topupOptions: null,
      deviceTopupOptions: null,
      changeOptions: null,
      selectedMethod: "card",
    });
  });
});
