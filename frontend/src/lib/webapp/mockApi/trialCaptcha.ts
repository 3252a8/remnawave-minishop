import image from "./trialCaptcha.png?inline";
import { DEV_MOCK } from "../previewMock.js";
import { jsonBody } from "../demoMockRuntime.js";

let challenge = 0;
let verifiedUntil = 0;
let issuedAt = 0;

export function trialCaptchaDemoResponse(path: string, options: RequestInit): unknown {
  const enabled = DEV_MOCK.data.settings.trial_captcha_enabled === true;
  const method = String(options.method || "GET").toUpperCase();
  if (path === "/trial/captcha" && method === "GET") {
    const required = enabled && Date.now() >= verifiedUntil;
    if (required) {
      challenge += 1;
      issuedAt = Date.now();
    }
    return {
      ok: true,
      required,
      challenge_id: required ? `demo-trial-${challenge}` : null,
      image: required ? image : null,
      expires_in_seconds: required ? 180 : 0,
    };
  }
  if (path === "/trial/captcha/verify" && method === "POST") {
    const body = jsonBody(options);
    if (body.challenge_id !== `demo-trial-${challenge}` || Date.now() - issuedAt >= 180_000)
      return { ok: false, error: "trial_captcha_expired" };
    issuedAt = 0;
    if (String(body.answer || "").trim() !== "73146")
      return { ok: false, error: "trial_captcha_invalid" };
    verifiedUntil = Date.now() + 600_000;
    return { ok: true };
  }
  if (
    enabled &&
    Date.now() >= verifiedUntil &&
    method === "POST" &&
    (path === "/trial/activate" ||
      (path === "/payments" && jsonBody(options).sale_mode === "trial"))
  )
    return { ok: false, error: "trial_captcha_required" };
  return undefined;
}
