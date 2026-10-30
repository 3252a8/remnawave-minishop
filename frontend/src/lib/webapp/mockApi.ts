import { buildAdminDemoFixtures } from "./mockApi/adminFixtures";
import { adminFallbackResponse } from "./mockApi/adminFallback";
import { defaultClone, type MockApiContext } from "./mockApi/dataset";
import { demoApiResponse } from "./mockApi/datasetApi";
import { partnerProgramDemoResponse } from "./mockApi/partnerProgramResponse";
import { webappFallbackResponse } from "./mockApi/webappFallback";
import { giftsDemoResponse } from "./mockApi/giftsDemo";
import { advertisingDemoResponse } from "./mockApi/advertisingDemo";
import { telegramMenuDemoResponse } from "./mockApi/telegramMenuDemo";
import { accountMergeDemoResponse } from "./mockApi/accountMerge";
import { issueReviewDemoResponse } from "./mockApi/issueReview";
import { demoPaymentHistoryItems, paymentHistoryDemoResponse } from "./mockApi/paymentHistory";
import { DATASET } from "./mockApi/dataset";
import { trialCaptchaDemoResponse } from "./mockApi/trialCaptcha";
import { paymentFallbackDemoResponse } from "./mockApi/paymentFallback.js";
import { subscriptionDaysDemoResponse } from "./mockApi/subscriptionDays.js";

export async function mockApi(
  path: string,
  options: RequestInit = {},
  context: MockApiContext = {}
): Promise<unknown> {
  const {
    currentLang = "ru",
    normalizeLangCode = (value: unknown) => String(value || "ru"),
    clone = defaultClone,
  } = context;
  await new Promise((resolve) => window.setTimeout(resolve, 120));
  const cleanPath = String(path || "").split("?")[0];
  if (cleanPath === "/support/payment-options") {
    const scenario = new URLSearchParams(window.location.search).get("mock");
    if (scenario === "support-payments-error") return { ok: false, error: "unavailable" };
    return {
      ok: true,
      recent_days: 7,
      items: (scenario === "support-payments-empty"
        ? []
        : demoPaymentHistoryItems(Number(DATASET.currentUser?.user_id))
      )
        .filter((item) => !["completed", "refunded"].includes(item.history_state))
        .slice(0, 100)
        .map(({ payment_id, amount, currency, provider, created_at, history_state }) => ({
          payment_id,
          amount,
          currency,
          provider,
          created_at,
          history_state,
        })),
    };
  }
  const subscriptionDays = subscriptionDaysDemoResponse(path, options);
  if (subscriptionDays !== undefined) return subscriptionDays;
  const paymentFallback = paymentFallbackDemoResponse(cleanPath, options);
  if (paymentFallback !== undefined) return paymentFallback;
  const trialCaptcha = trialCaptchaDemoResponse(cleanPath, options);
  if (trialCaptcha !== undefined) return trialCaptcha;
  const paymentHistory = paymentHistoryDemoResponse(path);
  if (paymentHistory !== undefined) return paymentHistory;
  const issueReview = issueReviewDemoResponse(path, options, currentLang);
  if (issueReview !== undefined) return issueReview;
  const mergeResponse = accountMergeDemoResponse(cleanPath, options);
  if (mergeResponse !== undefined) return mergeResponse;
  const telegramMenu = telegramMenuDemoResponse(path, options);
  if (telegramMenu !== undefined) return telegramMenu;
  const advertising = advertisingDemoResponse(path, options);
  if (advertising !== undefined) return advertising;
  if (cleanPath === "/theme-effects") return { ok: true, effect: null };
  const giftsResponse = giftsDemoResponse(cleanPath, options, path);
  if (giftsResponse !== undefined) return giftsResponse;
  const resolvedContext: MockApiContext = { clone, currentLang, normalizeLangCode };
  const demoResponse = demoApiResponse(path, cleanPath, options, resolvedContext);
  if (demoResponse !== undefined) return demoResponse;
  const partnerResponse = partnerProgramDemoResponse(path, cleanPath, options, resolvedContext);
  if (partnerResponse !== undefined) return partnerResponse;
  const fixtures = buildAdminDemoFixtures();
  const adminResponse = adminFallbackResponse(path, cleanPath, options, resolvedContext, fixtures);
  if (adminResponse !== undefined) return adminResponse;
  return webappFallbackResponse(path, cleanPath, options, resolvedContext, fixtures);
}
