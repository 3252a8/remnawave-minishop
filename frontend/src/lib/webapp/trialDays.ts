export type TrialDaysStrategy = "add_remaining" | "start_from_payment";

type TrialSubscriptionLike = {
  active?: unknown;
  provider?: unknown;
  status?: unknown;
};

export function isActiveTrialSubscription(subscription: TrialSubscriptionLike): boolean {
  const provider = String(subscription?.provider || "").toLowerCase();
  const status = String(subscription?.status || "").toUpperCase();
  return Boolean(subscription?.active && (provider === "trial" || status.includes("TRIAL")));
}
