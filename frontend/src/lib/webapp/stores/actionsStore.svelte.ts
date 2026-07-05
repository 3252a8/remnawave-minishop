import type { LoadDataOptions } from "../dataClient";
import type { ApiClient, PostPayload, TrialActivateResponse } from "../publicApi";
import {
  buildPromoApplyPath,
  buildPromoStatusPath,
  buildReferralWelcomeBonusClaimPath,
  buildTrialActivatePath,
  unwrap,
} from "../publicApi";

type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type MaybeRecord = Record<string, unknown>;
export type PromoDeeplinkStatus = "" | "standalone" | "already_used" | "invalid" | "error";
export type PromoDeeplinkContext = { modalOpened?: boolean };
export type ActionsState = {
  promoCode: string;
  promoBusy: boolean;
  promoStatus: string;
  promoIsError: boolean;
  promoFieldError: string;
  promoCheckoutCode: string;
  promoCheckoutSummary: string;
  promoDeeplinkOpen: boolean;
  promoDeeplinkStatus: PromoDeeplinkStatus;
  promoDeeplinkCode: string;
  promoDeeplinkMessage: string;
  promoDeeplinkEffectSummary: string;
  promoDeeplinkError: string;
  promoDeeplinkBusy: boolean;
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
  prefillCheckoutPromo?: (code: string) => void;
};
export type ActionsStore = ActionsState & {
  setPromoCode(value: string): void;
  setPromoFieldError(value: string): void;
  clearPromoFieldError(): void;
  applyPromo(): Promise<void>;
  openPromoCheckout(): void;
  handlePromoDeeplink(code: string, context?: PromoDeeplinkContext): Promise<void>;
  activatePromoDeeplink(): Promise<void>;
  closePromoDeeplink(): void;
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
  prefillCheckoutPromo = () => {},
}: ActionsStoreDeps) {
  const state = $state<ActionsStore>({
    promoCode: "",
    promoBusy: false,
    promoStatus: "",
    promoIsError: false,
    promoFieldError: "",
    promoCheckoutCode: "",
    promoCheckoutSummary: "",
    promoDeeplinkOpen: false,
    promoDeeplinkStatus: "",
    promoDeeplinkCode: "",
    promoDeeplinkMessage: "",
    promoDeeplinkEffectSummary: "",
    promoDeeplinkError: "",
    promoDeeplinkBusy: false,
    trialBusy: false,
    trialActivationResult: null,
    trialActivationError: "",
    setPromoCode,
    setPromoFieldError,
    clearPromoFieldError,
    applyPromo,
    openPromoCheckout,
    handlePromoDeeplink,
    activatePromoDeeplink,
    closePromoDeeplink,
    claimReferralWelcomeBonus,
    activateTrial,
  });

  function setPromoCode(value: string) {
    state.promoCode = value;
    state.promoStatus = "";
    state.promoIsError = false;
    state.promoFieldError = "";
    state.promoCheckoutCode = "";
    state.promoCheckoutSummary = "";
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
        startCheckoutPromo(state.promoCheckoutCode);
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

  function openPromoDeeplinkDialog(
    status: PromoDeeplinkStatus,
    code: string,
    message = "",
    effectSummary = ""
  ) {
    state.promoDeeplinkOpen = true;
    state.promoDeeplinkStatus = status;
    state.promoDeeplinkCode = code;
    state.promoDeeplinkMessage = message;
    state.promoDeeplinkEffectSummary = effectSummary;
    state.promoDeeplinkError = "";
    state.promoDeeplinkBusy = false;
  }

  function closePromoDeeplink() {
    state.promoDeeplinkOpen = false;
    state.promoDeeplinkStatus = "";
    state.promoDeeplinkCode = "";
    state.promoDeeplinkMessage = "";
    state.promoDeeplinkEffectSummary = "";
    state.promoDeeplinkError = "";
    state.promoDeeplinkBusy = false;
  }

  async function handlePromoDeeplink(code: string, context: PromoDeeplinkContext = {}) {
    const trimmed = String(code || "").trim();
    if (!trimmed) return;
    try {
      const payload: PostPayload<"/api/promo/status"> = { code: trimmed };
      const response = await api(buildPromoStatusPath(), {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const statusPayload = asRecord(unwrap(response));
      const status = stringField(statusPayload.status);
      const resolvedCode = stringField(statusPayload.code) || trimmed;
      const message = stringField(statusPayload.message);
      const effectSummary = stringField(statusPayload.effect_summary);
      if (status === "requires_checkout") {
        // The code adjusts a purchase — the checkout flow with the prefilled
        // code stays the right UX. Reuse the opened deeplink modal if any.
        if (context.modalOpened) {
          prefillCheckoutPromo(resolvedCode);
        } else {
          startCheckoutPromo(resolvedCode);
        }
        return;
      }
      if (status === "standalone") {
        openPromoDeeplinkDialog("standalone", resolvedCode, message, effectSummary);
        return;
      }
      if (status === "already_used") {
        openPromoDeeplinkDialog("already_used", resolvedCode, message);
        return;
      }
      // not_found / throttled / anything unexpected: explain instead of
      // dropping the user into a checkout with a failing promo field.
      openPromoDeeplinkDialog(
        "invalid",
        resolvedCode,
        message || t("wa_promo_activation_failed", {}, "Failed to activate promo code")
      );
    } catch (error: unknown) {
      openPromoDeeplinkDialog(
        "error",
        trimmed,
        stringField(asRecord(error).message) ||
          t(
            "wa_promo_deeplink_check_failed",
            {},
            "Check your connection and try again — or enter the code manually on the home screen."
          )
      );
    }
  }

  async function activatePromoDeeplink() {
    const code = String(state.promoDeeplinkCode || "").trim();
    if (!code || state.promoDeeplinkBusy) return;
    state.promoDeeplinkBusy = true;
    state.promoDeeplinkError = "";
    try {
      const payload: PostPayload<"/api/promo/apply"> = { code };
      const response = await api(buildPromoApplyPath(), {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const responsePayload = asRecord(unwrap(response));
      if (responsePayload.requires_checkout === true) {
        // Race: the code switched to checkout-only between check and apply.
        closePromoDeeplink();
        startCheckoutPromo(stringField(responsePayload.code) || code);
        return;
      }
      closePromoDeeplink();
      const endDateText = stringField(responsePayload.end_date_text);
      showToast(
        endDateText ? t("wa_promo_activated_until", { date: endDateText }) : t("wa_promo_activated")
      );
      await loadData({ fresh: true });
    } catch (error: unknown) {
      state.promoDeeplinkError =
        stringField(asRecord(error).message) || t("wa_promo_activation_failed");
    } finally {
      state.promoDeeplinkBusy = false;
    }
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
