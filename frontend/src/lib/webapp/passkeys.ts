import type { ApiClient } from "./publicApi.js";

type JsonMap = Record<string, unknown>;

function decodeBase64Url(value: unknown): ArrayBuffer {
  const normalized = String(value || "")
    .replace(/-/g, "+")
    .replace(/_/g, "/");
  const binary = atob(normalized + "=".repeat((4 - (normalized.length % 4)) % 4));
  return Uint8Array.from(binary, (char) => char.charCodeAt(0)).buffer;
}

function encodeBase64Url(value: ArrayBuffer): string {
  const bytes = new Uint8Array(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function creationOptions(value: JsonMap): PublicKeyCredentialCreationOptions {
  const options = structuredClone(value) as unknown as PublicKeyCredentialCreationOptions;
  options.challenge = decodeBase64Url(value.challenge);
  const user = value.user as JsonMap;
  options.user = { ...user, id: decodeBase64Url(user.id) } as PublicKeyCredentialUserEntity;
  options.excludeCredentials = ((value.excludeCredentials as JsonMap[]) || []).map((item) => ({
    ...item,
    id: decodeBase64Url(item.id),
  })) as PublicKeyCredentialDescriptor[];
  return options;
}

function requestOptions(value: JsonMap): PublicKeyCredentialRequestOptions {
  const options = structuredClone(value) as unknown as PublicKeyCredentialRequestOptions;
  options.challenge = decodeBase64Url(value.challenge);
  options.allowCredentials = ((value.allowCredentials as JsonMap[]) || []).map((item) => ({
    ...item,
    id: decodeBase64Url(item.id),
  })) as PublicKeyCredentialDescriptor[];
  return options;
}

function serializeCredential(credential: PublicKeyCredential): JsonMap {
  const response = credential.response;
  const serialized: JsonMap = {
    id: credential.id,
    rawId: encodeBase64Url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment,
    clientExtensionResults: credential.getClientExtensionResults(),
  };
  if (response instanceof AuthenticatorAttestationResponse) {
    serialized.response = {
      clientDataJSON: encodeBase64Url(response.clientDataJSON),
      attestationObject: encodeBase64Url(response.attestationObject),
      transports: response.getTransports?.() || [],
    };
  } else if (response instanceof AuthenticatorAssertionResponse) {
    serialized.response = {
      clientDataJSON: encodeBase64Url(response.clientDataJSON),
      authenticatorData: encodeBase64Url(response.authenticatorData),
      signature: encodeBase64Url(response.signature),
      userHandle: response.userHandle ? encodeBase64Url(response.userHandle) : null,
    };
  }
  return serialized;
}

function challengeFrom(options: JsonMap): string {
  return String(options.challenge || "");
}

function currentPlatform(): string {
  const browserNavigator = navigator as Navigator & {
    userAgentData?: { platform?: string };
  };
  return String(browserNavigator.userAgentData?.platform || browserNavigator.platform || "");
}

function platformLabel(platform: unknown): string {
  const value = String(platform || "").trim();
  const normalized = value.toLowerCase();
  if (!normalized) return "";
  if (normalized.includes("iphone")) return "iPhone";
  if (normalized.includes("ipad")) return "iPad";
  if (normalized.includes("android")) return "Android";
  if (normalized.includes("win")) return "Windows";
  if (normalized.includes("mac")) return "macOS";
  if (normalized.includes("cros") || normalized.includes("chrome os")) return "ChromeOS";
  if (normalized.includes("linux")) return "Linux";
  return value;
}

export function suggestedPasskeyName(serviceName: unknown, platform: unknown): string {
  const service = String(serviceName || "").trim() || "Passkey";
  const device = platformLabel(platform);
  return `${service}${device ? ` · ${device}` : ""}`.slice(0, 80);
}

export function passkeysSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "PublicKeyCredential" in window &&
    Boolean(navigator.credentials)
  );
}

export async function registerPasskey(
  api: ApiClient["api"],
  fallbackServiceName = "Passkey"
): Promise<void> {
  if (!passkeysSupported()) throw new Error("passkey_unsupported");
  const optionsResponse = await api("/account/passkeys/options", {
    method: "POST",
    body: JSON.stringify({}),
  });
  if (!optionsResponse.ok) throw optionsResponse;
  const rawOptions = optionsResponse.options as JsonMap;
  const rp = (rawOptions.rp || {}) as JsonMap;
  const name = suggestedPasskeyName(fallbackServiceName || rp.name, currentPlatform());
  const credential = (await navigator.credentials.create({
    publicKey: creationOptions(rawOptions),
  })) as PublicKeyCredential | null;
  if (!credential) throw new Error("passkey_cancelled");
  const response = await api("/account/passkeys/register", {
    method: "POST",
    body: JSON.stringify({
      challenge: challengeFrom(rawOptions),
      credential: serializeCredential(credential),
      name,
    }),
  });
  if (!response.ok) throw response;
}

function publicApiUrl(apiBase: string, path: string): string {
  const base = String(apiBase || "/api").replace(/\/+$/, "");
  return `${base}/${path.replace(/^\/+/, "")}`;
}

export async function loginWithPasskey(apiBase = "/api"): Promise<void> {
  if (!passkeysSupported()) throw new Error("passkey_unsupported");
  const optionsResponse = await fetch(publicApiUrl(apiBase, "/auth/passkey/options"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
    credentials: "same-origin",
  }).then((response) => response.json());
  if (!optionsResponse.ok) throw optionsResponse;
  const rawOptions = optionsResponse.options as JsonMap;
  const credential = (await navigator.credentials.get({
    publicKey: requestOptions(rawOptions),
  })) as PublicKeyCredential | null;
  if (!credential) throw new Error("passkey_cancelled");
  const verifyResponse = await fetch(publicApiUrl(apiBase, "/auth/passkey/verify"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      challenge: challengeFrom(rawOptions),
      credential: serializeCredential(credential),
    }),
    credentials: "same-origin",
  }).then((response) => response.json());
  if (!verifyResponse.ok) throw verifyResponse;
  window.location.assign("/home");
}
