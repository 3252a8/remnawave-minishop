import { DEV_MOCK } from "../previewMock.js";
import { jsonBody } from "../demoMockRuntime.js";
import { demoAuthConfig } from "./authDemo";

const initialParams = new URLSearchParams(
  typeof window === "undefined" ? "" : window.location.search
);
const externalStatus = initialParams.get("external_auth") || "";
const telegramStatus = initialParams.get("telegram_auth") || "";
const scenario = initialParams.get("merge_demo") || "";
let pending =
  externalStatus.includes("account_merge_") || telegramStatus.startsWith("account_merge_");
const sourceProvider = externalStatus.split(":")[0] || "telegram";
let confirmed =
  externalStatus.endsWith(":account_merge_ready") || telegramStatus === "account_merge_ready";

export function accountMergeDemoResponse(path: string, options: RequestInit): unknown {
  if (!path.startsWith("/account/merge/")) return undefined;
  const method = String(options.method || "GET").toUpperCase();
  const emailAvailable = scenario !== "provider-only";
  if (path === "/account/merge/cancel" && method === "POST") {
    pending = false;
    confirmed = false;
    return { ok: true };
  }
  if (!pending) return { ok: false, error: "account_merge_not_required" };
  if (path === "/account/merge/passkey/options" && method === "POST") {
    return {
      ok: true,
      options: {
        challenge: "AQID",
        rpId: window.location.hostname,
        userVerification: "required",
      },
    };
  }
  if (path === "/account/merge/passkey/verify" && method === "POST") {
    const body = jsonBody(options);
    if (!body.challenge || !body.credential) return { ok: false, error: "invalid_credential" };
    confirmed = true;
    return { ok: true };
  }
  if (path === "/account/merge/status" && method === "GET") {
    return {
      ok: true,
      provider: sourceProvider,
      providers:
        scenario === "future"
          ? ["future-provider"]
          : ["google", "discord", "yandex", "telegram", "passkey"],
      target_confirmed: confirmed,
      email_available: emailAvailable,
      email: emailAvailable ? String(DEV_MOCK.data.user.email || demoAuthConfig().email) : null,
    };
  }
  if (path === "/account/merge/request" && method === "POST") {
    return emailAvailable
      ? { ok: true, email_code: demoAuthConfig().code }
      : { ok: false, error: "verified_email_required" };
  }
  if (path === "/account/merge/confirm" && method === "POST") {
    if (!confirmed && String(jsonBody(options).email_code || "") !== demoAuthConfig().code)
      return { ok: false, error: "invalid_code" };
    pending = false;
    confirmed = false;
    return { ok: true, csrf_token: "local-preview-csrf" };
  }
  return { ok: false, error: "not_found" };
}
