import { describe, expect, it, vi } from "vitest";
import { createTrialCaptchaStore } from "./trialCaptchaStore.svelte.js";

const challenge = {
  ok: true,
  required: true,
  challenge_id: "challenge-1",
  image: "data:image/png;base64,fixture",
  expires_in_seconds: 180,
};
const t = (key: string) => key;

describe("trial verification", () => {
  it("continues without a dialog when verification is disabled or already valid", async () => {
    const api = vi.fn().mockResolvedValue({ ok: true, required: false });
    const store = createTrialCaptchaStore(api, t);
    expect(await store.ensure()).toBe(true);
    expect(store.open).toBe(false);
  });

  it("shares a pending challenge and continues only after a successful answer", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce(challenge)
      .mockResolvedValueOnce({ ok: false, error: "trial_captcha_invalid" })
      .mockResolvedValueOnce({ ...challenge, challenge_id: "challenge-2" })
      .mockResolvedValueOnce({ ok: true });
    const store = createTrialCaptchaStore(api, t);
    const verified = store.ensure();
    expect(store.ensure()).toBe(verified);
    await vi.waitFor(() => expect(store.open).toBe(true));
    store.answer = "00000";
    await store.verify();
    expect(store.error).toBe("wa_trial_captcha_invalid");
    expect(store.open).toBe(true);
    store.answer = " 73146 ";
    await store.verify();
    expect(await verified).toBe(true);
    expect(store.open).toBe(false);
    expect(api).toHaveBeenLastCalledWith("/trial/captcha/verify", {
      method: "POST",
      body: JSON.stringify({ challenge_id: "challenge-2", answer: "73146" }),
    });
  });

  it("cancels the action and ignores a challenge returned after cancellation", async () => {
    let resolveRequest: (value: typeof challenge) => void = () => {};
    const request = new Promise<typeof challenge>((resolve) => (resolveRequest = resolve));
    const api = vi.fn().mockReturnValue(request);
    const store = createTrialCaptchaStore(api, t);
    const verified = store.ensure();
    store.cancel();
    resolveRequest(challenge);
    expect(await verified).toBe(false);
    await Promise.resolve();
    expect(store.open).toBe(false);
    expect(store.challengeId).toBe("");
  });

  it("requires a new image after expiry and discards an answer when refreshing", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce(challenge)
      .mockResolvedValueOnce({ ok: false, error: "trial_captcha_expired" })
      .mockResolvedValueOnce({ ...challenge, challenge_id: "challenge-2" })
      .mockResolvedValueOnce({ ...challenge, challenge_id: "challenge-3" });
    const store = createTrialCaptchaStore(api, t);
    const verified = store.ensure();
    await vi.waitFor(() => expect(store.open).toBe(true));
    store.answer = "73146";
    await store.verify();
    expect(store.error).toBe("wa_trial_captcha_expired");
    expect(store.challengeId).toBe("challenge-2");
    await store.refresh();
    expect(store.challengeId).toBe("challenge-3");
    expect(store.answer).toBe("");
    expect(store.error).toBe("");
    store.cancel();
    expect(await verified).toBe(false);
  });

  it.each(["trial_captcha_rate_limited", "trial_captcha_unavailable"])(
    "keeps the action blocked while %s is displayed",
    async (error) => {
      const api = vi.fn().mockResolvedValue({ ok: false, error });
      const store = createTrialCaptchaStore(api, t);
      const verified = store.ensure();
      await vi.waitFor(() => expect(store.open).toBe(true));
      expect(store.error).toBe(error.replace("trial_", "wa_trial_"));
      store.cancel();
      expect(await verified).toBe(false);
    }
  );
});
