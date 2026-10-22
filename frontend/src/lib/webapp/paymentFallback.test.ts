import { afterEach, describe, expect, it, vi } from "vitest";
import { nextCheckoutPaymentMethod, paymentProviderUnavailable } from "./paymentFallback.js";
import { createApiClient } from "./publicApi.js";
import { methodsForPlan } from "./tariffs.js";
import type { PaymentMethodGroup, PaymentMethodView } from "./types.js";

afterEach(() => vi.unstubAllGlobals());

describe("checkout payment fallback", () => {
  const methods: PaymentMethodView[] = [
    { id: "before", group: "fiat", provider_id: "before_service" },
    { id: "wata", group: "fiat", provider_id: "wata_service" },
    { id: "crypto", group: "crypto", provider_id: "crypto_service" },
    { id: "wata_card", group: "fiat", provider_id: "wata_service" },
    { id: "card", group: "fiat", provider_id: "card_service" },
    { id: "stars", group: "stars", provider_id: "stars_service" },
    { id: "mixed", group: "mixed", provider_id: "mixed_service" },
  ];

  it("continues in configured order, wraps and excludes the entire failed chain", () => {
    expect(nextCheckoutPaymentMethod(methods, ["wata"])?.id).toBe("card");
    expect(nextCheckoutPaymentMethod(methods, ["wata", "card"])?.id).toBe("before");
    expect(nextCheckoutPaymentMethod(methods, ["wata", "card", "before"])).toBeNull();
  });

  it.each(["fiat", "crypto", "stars", "mixed"] as PaymentMethodGroup[])(
    "keeps %s payments within their group even when another group comes first",
    (group) => {
      const choices: PaymentMethodView[] = [
        { id: "failed", group, provider_id: "first" },
        { id: "different", group: group === "fiat" ? "crypto" : "fiat", provider_id: "different" },
        { id: "same-provider", group, provider_id: "first" },
        { id: "alternative", group, provider_id: "second" },
      ];
      expect(nextCheckoutPaymentMethod(choices, ["failed"])?.id).toBe("alternative");
      expect(nextCheckoutPaymentMethod(choices, ["failed", "alternative"])).toBeNull();
    }
  );

  it("excludes providers from the full failure chain and normalizes their identifiers", () => {
    const choices: PaymentMethodView[] = [
      { id: "wata", group: "fiat", provider_id: " WATA_SERVICE " },
      { id: "card", group: "fiat", provider_id: "CARD_SERVICE" },
      { id: "wata_sbp", group: "fiat", provider_id: "wata_service" },
      { id: "card_sbp", group: "fiat", provider_id: "card_service" },
      { id: "other", group: "fiat", provider_id: "other" },
    ];
    expect(nextCheckoutPaymentMethod(choices, ["WATA", "CARD"])?.id).toBe("other");
    expect(nextCheckoutPaymentMethod(choices, ["wata", "card"], ["OTHER"])).toBeNull();
  });

  it("uses separate normalized method IDs when provider metadata is missing", () => {
    const choices: PaymentMethodView[] = [
      { id: "WATA", group: "fiat" },
      { id: "card", group: "fiat" },
    ];
    expect(nextCheckoutPaymentMethod(choices, ["wata"])?.id).toBe("card");
  });

  it("does not guess a provider when an earlier rejected method disappears from eligibility", () => {
    expect(nextCheckoutPaymentMethod(methods, ["hidden-failed", "card"])).toBeNull();
  });

  it.each([undefined, null, "unknown"])(
    "does not suggest a method for an unknown group (%s)",
    (group) => {
      const choices = [
        { id: "failed", group },
        { id: "alternative", group },
      ] as unknown as PaymentMethodView[];
      expect(nextCheckoutPaymentMethod(choices, ["failed"])).toBeNull();
      expect(nextCheckoutPaymentMethod(methods, ["missing-method"])).toBeNull();
    }
  );

  it("respects plan visibility, minimums, balance compatibility and add-on exclusions", () => {
    const eligible = methodsForPlan(
      [
        { id: "wata", group: "fiat" },
        { id: "hidden", group: "fiat" },
        { id: "expensive", group: "fiat", min_amount: 500, min_currency: "RUB" },
        { id: "subscription", group: "fiat", balance_supported: false },
        { id: "no-addons", group: "fiat" },
        { id: "card", group: "fiat" },
      ],
      {
        price: 290,
        currency: "RUB",
        available_payment_method_ids: ["wata", "expensive", "subscription", "no-addons", "card"],
      },
      "user"
    );
    expect(nextCheckoutPaymentMethod(eligible, ["wata"], ["no-addons"])?.id).toBe("card");
    expect(nextCheckoutPaymentMethod([], ["wata"])).toBeNull();
    expect(nextCheckoutPaymentMethod(methods, [])).toBeNull();
  });

  it("accepts only the definitive provider failure code", () => {
    expect(paymentProviderUnavailable({ error: "payment_provider_unavailable" })).toBe(true);
    for (const error of [
      null,
      new Error("offline"),
      { error: "payment_failed" },
      { error: "invalid_plan" },
      { message: "payment_provider_unavailable" },
    ]) {
      expect(paymentProviderUnavailable(error)).toBe(false);
    }
  });

  it("recognizes the provider rejection wrapped by the real HTTP client", async () => {
    const payload = { ok: false, error: "payment_provider_unavailable" };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json(payload, { status: 502 }))
    );
    const client = createApiClient();
    const error = await client.api("/payments", { method: "POST" }).catch((cause) => cause);

    expect(error).toMatchObject({ message: "service_unavailable", status: 502, payload });
    expect(paymentProviderUnavailable(error)).toBe(true);
  });

  it.each([
    { status: 502, payload: { ok: false, error: "payment_failed" } },
    { status: 502, payload: { ok: true, error: "payment_provider_unavailable" } },
    { status: 502, payload: { error: "payment_provider_unavailable" } },
    { status: 503, payload: { ok: false, error: "payment_provider_unavailable" } },
    { status: 429, payload: { ok: false, error: "payment_provider_unavailable" } },
    { status: 502, payload: null },
  ])("does not treat an unrelated HTTP failure as a provider rejection (%o)", (error) => {
    expect(paymentProviderUnavailable(Object.assign(new Error("service_unavailable"), error))).toBe(
      false
    );
  });
});
