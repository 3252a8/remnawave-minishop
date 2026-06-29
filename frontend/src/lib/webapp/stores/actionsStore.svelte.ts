import type { LoadDataOptions } from "../dataClient";
import type { ApiClient, PostPayload, TrialActivateResponse } from "../publicApi";
import {
  buildPromoApplyPath,
  buildReferralWelcomeBonusClaimPath,
  buildTrialActivatePath,
  unwrap,
} from "../publicApi";

type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type MaybeRecord = Record<string, unknown>;
export type ActionsState = {
  promoCode: string;
  promoBusy: boolean;
  promoStatus: string;
  promoIsError: boolean;
  promoFieldError: string;
  promoCheckoutCode: string;
  promoCheckoutSummary: string;
  trialBusy: boolean;
  trialActivationResult: Extract<TrialActivateResponse, { ok: true }> | null;
  trialActivationError: string;
};
type ActionsStoreDeps = {
  api: ApiClient["api"];
  t: Translate;
  showToast: (message: string) => void;
  loadData: (options?: LoadDataOptions & Record<string, unknown>) => Promise<unknown>;
  maybeShowActivationSuccessDialog: (context?: Record<string, unknown>) => Promise<boolean>;
  startCheckoutPromo?: (code: string) => void;
};
export type ActionsStore = ActionsState & {
  setPromoCode(value: string): void;
  setPromoFieldError(value: string): void;
  clearPromoFieldError(): void;
  applyPromo(): Promise<void>;
  openPromoCheckout(): void;
  claimReferralWelcomeBonus(): Promise<void>;
  activateTrial(): Promise<void>;
};

function asRecord(value: unknown): MaybeRecord {
  return value && typeof value === "object" ? (value as MaybeRecord) : {};
}

function stringField(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function createActionsStore({
  api,
  t,
  showToast,
  loadData,
  maybeShowActivationSuccessDialog,
  startCheckoutPromo = () => {},
}: ActionsStoreDeps) {
  const state = $state<ActionsStore>({
    promoCode: "",
    promoBusy: false,
    promoStatus: "",
    promoIsError: false,
    promoFieldError: "",
    promoCheckoutCode: "",
    promoCheckoutSummary: "",
    trialBusy: false,
    trialActivationResult: null,
    trialActivationError: "",
    setPromoCode,
    setPromoFieldError,
    clearPromoFieldError,
    applyPromo,
    openPromoCheckout,
    claimReferralWelcomeBonus,
    activateTrial,
  });

  function setPromoCode(value: string) {
    state.promoCode = value;
  }

  function setPromoFieldError(value: string) {
    state.promoFieldError = value;
  }

  function clearPromoFieldError() {
    setPromoFieldError("");
  }

  function trialActivationFailureMessage(error: unknown) {
    const errorRecord = asRecord(error);
    if (
      errorRecord.error === "trial_telegram_required" ||
      errorRecord.message === "telegram_required" ||
      errorRecord.message === "disposable_email"
    ) {
      return t(
        "wa_trial_telegram_required_error",
        {},
        "Для активации пробного периода привяжите Telegram."
      );
    }
    return stringField(errorRecord.message) || t("wa_trial_activation_failed");
  }

  function referralWelcomeFailureMessage(error: unknown) {
    const errorRecord = asRecord(error);
    if (
      errorRecord.error === "referral_welcome_telegram_required" ||
      errorRecord.message === "telegram_required" ||
      errorRecord.message === "disposable_email"
    ) {
      return t(
        "wa_referral_welcome_telegram_required_error",
        {},
        "Для получения реферального бонуса привяжите Telegram."
      );
    }
    return stringField(errorRecord.message) || t("wa_referral_welcome_claim_failed");
  }

  async function applyPromo() {
    const code = state.promoCode.trim();
    if (!code) {
      setPromoFieldError(t("wa_promo_enter"));
      return;
    }
    state.promoFieldError = "";
    state.promoBusy = true;
    state.promoStatus = "";
    state.promoCheckoutCode = "";
    state.promoCheckoutSummary = "";
    try {
      const payload: PostPayload<"/api/promo/apply"> = { code };
      const response = await api(buildPromoApplyPath(), {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const responsePayload = unwrap(response);
      const payloadRecord = asRecord(responsePayload);
      if (payloadRecord.requires_checkout === true) {
        const summary = stringField(payloadRecord.effect_summary);
        state.promoCheckoutCode = stringField(payloadRecord.code) || code;
        state.promoCheckoutSummary = summary;
        state.promoStatus =
          summary || t("promo_code_requires_checkout", {}, "Apply this code at checkout.");
        state.promoIsError = false;
        return;
      }
      state.promoCode = "";
      const endDateText = stringField(payloadRecord.end_date_text);
      state.promoStatus = endDateText
        ? t("wa_promo_activated_until", { date: endDateText })
        : t("wa_promo_activated");
      state.promoIsError = false;
      await loadData({ fresh: true });
    } catch (error: unknown) {
      const message = stringField(asRecord(error).message) || t("wa_promo_activation_failed");
      state.promoStatus = message;
      state.promoIsError = true;
      state.promoFieldError = message;
    } finally {
      state.promoBusy = false;
    }
  }

  function openPromoCheckout() {
    const code = String(state.promoCheckoutCode || state.promoCode || "").trim();
    if (!code) return;
    startCheckoutPromo(code);
  }

  async function claimReferralWelcomeBonus() {
    try {
      const response = await api(buildReferralWelcomeBonusClaimPath(), {
        method: "POST",
        body: JSON.stringify({} as PostPayload<"/api/referral/welcome-bonus/claim">),
      });
      const responsePayload = unwrap(response);
      showToast(
        responsePayload.end_date_text
          ? t("wa_referral_welcome_claimed_until", { date: responsePayload.end_date_text })
          : t("wa_referral_welcome_claimed")
      );
      await loadData({ fresh: true });
      await maybeShowActivationSuccessDialog({ source: "referral_welcome", force: true });
    } catch (error: unknown) {
      showToast(referralWelcomeFailureMessage(error));
    }
  }

  async function activateTrial() {
    if (state.trialBusy) return;
    state.trialBusy = true;
    state.trialActivationResult = null;
    state.trialActivationError = "";
    try {
      const response = await api(buildTrialActivatePath(), {
        method: "POST",
        body: JSON.stringify({} as PostPayload<"/api/trial/activate">),
      });
      const responsePayload = unwrap(response);
      state.trialActivationResult = responsePayload;
      showToast(t("wa_trial_activated"));
      await loadData({ fresh: true });
      await maybeShowActivationSuccessDialog({ source: "trial", force: true });
    } catch (error: unknown) {
      const message = trialActivationFailureMessage(error);
      state.trialActivationError = message;
      showToast(message);
    } finally {
      state.trialBusy = false;
    }
  }

  return state;
}
