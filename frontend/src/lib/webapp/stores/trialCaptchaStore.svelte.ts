import type { ApiClient } from "../publicApi.js";
import { unwrap } from "../publicApi.js";
import type { Translate } from "../types.js";

export type TrialCaptchaStore = {
  open: boolean;
  loading: boolean;
  verifying: boolean;
  challengeId: string;
  image: string;
  answer: string;
  error: string;
  ensure(): Promise<boolean>;
  refresh(): Promise<void>;
  verify(): Promise<void>;
  cancel(): void;
};

export function createTrialCaptchaStore(api: ApiClient["api"], t: Translate): TrialCaptchaStore {
  let generation = 0;
  let expiresAt = 0;
  let pending: Promise<boolean> | null = null;
  let resolvePending: ((verified: boolean) => void) | null = null;
  const state = $state<TrialCaptchaStore>({
    open: false,
    loading: false,
    verifying: false,
    challengeId: "",
    image: "",
    answer: "",
    error: "",
    ensure,
    refresh,
    verify,
    cancel: () => finish(false),
  });

  function finish(verified: boolean): void {
    generation += 1;
    state.open = false;
    state.loading = false;
    state.verifying = false;
    state.challengeId = "";
    state.image = "";
    state.answer = "";
    state.error = "";
    const resolve = resolvePending;
    resolvePending = null;
    pending = null;
    resolve?.(verified);
  }

  function errorMessage(error: unknown): string {
    const code = typeof error === "object" && error !== null && "error" in error ? error.error : "";
    if (code === "trial_captcha_invalid") return t("wa_trial_captcha_invalid");
    if (code === "trial_captcha_expired" || code === "trial_captcha_required")
      return t("wa_trial_captcha_expired");
    if (code === "trial_captcha_rate_limited") return t("wa_trial_captcha_rate_limited");
    return t("wa_trial_captcha_unavailable");
  }

  function ensure(): Promise<boolean> {
    if (pending) return pending;
    const result = new Promise<boolean>((resolve) => {
      resolvePending = resolve;
    });
    pending = result;
    void refresh();
    return result;
  }

  async function refresh(): Promise<void> {
    if (state.loading || state.verifying || !pending) return;
    const requestGeneration = ++generation;
    state.loading = true;
    state.error = "";
    state.answer = "";
    state.challengeId = "";
    state.image = "";
    try {
      const response = unwrap(await api("/trial/captcha"));
      if (generation !== requestGeneration) return;
      if (!response.required) {
        finish(true);
        return;
      }
      if (!response.challenge_id || !response.image?.startsWith("data:image/png;base64,"))
        throw new Error("invalid_captcha_challenge");
      state.challengeId = response.challenge_id;
      state.image = response.image;
      expiresAt = Date.now() + Math.max(0, response.expires_in_seconds) * 1000;
      state.open = true;
    } catch (error: unknown) {
      if (generation !== requestGeneration) return;
      state.error = errorMessage(error);
      state.open = true;
    } finally {
      if (generation === requestGeneration) state.loading = false;
    }
  }

  async function verify(): Promise<void> {
    if (
      state.loading ||
      state.verifying ||
      !state.challengeId ||
      !/^\d{5}$/.test(state.answer.trim())
    )
      return;
    if (Date.now() >= expiresAt) {
      await refresh();
      if (state.open && state.challengeId) state.error = t("wa_trial_captcha_expired");
      return;
    }
    const requestGeneration = generation;
    state.verifying = true;
    state.error = "";
    try {
      unwrap(
        await api("/trial/captcha/verify", {
          method: "POST",
          body: JSON.stringify({ challenge_id: state.challengeId, answer: state.answer.trim() }),
        })
      );
      if (generation === requestGeneration) finish(true);
    } catch (error: unknown) {
      if (generation !== requestGeneration) return;
      const message = errorMessage(error);
      state.error = message;
      state.answer = "";
      if (
        typeof error === "object" &&
        error !== null &&
        "error" in error &&
        (error.error === "trial_captcha_invalid" ||
          error.error === "trial_captcha_expired" ||
          error.error === "trial_captcha_required")
      ) {
        state.challengeId = "";
        state.image = "";
        state.verifying = false;
        await refresh();
        if (state.open && state.challengeId) state.error = message;
      }
    } finally {
      if (generation === requestGeneration) state.verifying = false;
    }
  }

  return state;
}
