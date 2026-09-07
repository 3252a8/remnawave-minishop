import { isTrialPaymentPlan } from "./tariffs.js";
import type { ApiClient, BalanceResponse } from "./publicApi.js";
import type { PlanView } from "./types.js";

export function checkoutBalanceLookupKey(plan: PlanView | null): string {
  if (!plan || isTrialPaymentPlan(plan) || Number(plan.price || 0) <= 0) return "";
  return String(plan.currency || "")
    .trim()
    .toUpperCase();
}

export function checkoutBalanceLookupPlan(
  selectedPlan: PlanView | null,
  selectedTariffPlans: PlanView[],
  plans: PlanView[]
): PlanView | null {
  return (
    selectedPlan ||
    selectedTariffPlans.find((plan) => Boolean(checkoutBalanceLookupKey(plan))) ||
    plans.find((plan) => Boolean(checkoutBalanceLookupKey(plan))) ||
    selectedTariffPlans[0] ||
    plans[0] ||
    null
  );
}

export function createCheckoutBalancePreload(
  getApi: () => ApiClient["api"],
  getOpen: () => boolean,
  getPlan: () => PlanView | null,
  onClose: () => void
) {
  let response = $state<BalanceResponse | null>(null);
  let ready = $state(false);
  let complete = $state(false);
  let activeKey = "";
  let requestId = 0;

  async function load(key: string, currentRequestId: number): Promise<void> {
    try {
      const nextResponse = (await getApi()("/balance")) as BalanceResponse;
      if (currentRequestId !== requestId || activeKey !== key) return;
      response = nextResponse;
    } catch {
      if (currentRequestId !== requestId || activeKey !== key) return;
      response = null;
    } finally {
      if (currentRequestId === requestId && activeKey === key) {
        complete = true;
        ready = true;
      }
    }
  }

  $effect(() => {
    const open = getOpen();
    const key = open ? checkoutBalanceLookupKey(getPlan()) : "";
    if (!open) {
      requestId += 1;
      activeKey = "";
      response = null;
      ready = false;
      complete = false;
      onClose();
      return;
    }
    if (!key) {
      requestId += 1;
      activeKey = "";
      response = null;
      ready = true;
      complete = true;
      return;
    }
    if (activeKey === key) return;
    activeKey = key;
    response = null;
    complete = false;
    const currentRequestId = ++requestId;
    void load(key, currentRequestId);
  });

  return {
    get response() {
      return response;
    },
    get ready() {
      return ready;
    },
    get complete() {
      return complete;
    },
  };
}
