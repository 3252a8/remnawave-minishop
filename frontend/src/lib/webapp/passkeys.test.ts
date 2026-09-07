import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApiClient } from "./publicApi.js";
import {
  loginWithPasskey,
  passkeyRegistrationBlockReason,
  registerPasskey,
  suggestedPasskeyName,
} from "./passkeys.js";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("suggestedPasskeyName", () => {
  it("combines the configured service name with a friendly platform label", () => {
    expect(suggestedPasskeyName(" /minishop ", "Win32")).toBe("/minishop · Windows");
    expect(suggestedPasskeyName("Tunnel", "MacIntel")).toBe("Tunnel · macOS");
  });

  it("falls back safely and stays within the backend storage limit", () => {
    expect(suggestedPasskeyName("", "")).toBe("Passkey");
    expect(suggestedPasskeyName("x".repeat(100), "Linux")).toHaveLength(80);
  });
});

describe("passkeyRegistrationBlockReason", () => {
  it("directs Telegram Mini App users to a regular browser", () => {
    expect(passkeyRegistrationBlockReason(true, true)).toBe("telegram_mini_app");
    expect(passkeyRegistrationBlockReason(true, false)).toBe("telegram_mini_app");
  });

  it("keeps regular browser support detection intact", () => {
    expect(passkeyRegistrationBlockReason(false, true)).toBe("");
    expect(passkeyRegistrationBlockReason(false, false)).toBe("unsupported");
  });
});

describe("registerPasskey", () => {
  it("registers the credential using the public service title and device name", async () => {
    class TestAttestationResponse {
      clientDataJSON = Uint8Array.from([1, 2]).buffer;
      attestationObject = Uint8Array.from([3, 4]).buffer;
      getTransports = () => ["internal"];
    }

    const credential = {
      id: "credential-id",
      rawId: Uint8Array.from([5, 6]).buffer,
      type: "public-key",
      authenticatorAttachment: "platform",
      getClientExtensionResults: () => ({}),
      response: new TestAttestationResponse(),
    };
    const create = vi.fn().mockResolvedValue(credential);
    vi.stubGlobal("window", { PublicKeyCredential: class {} });
    vi.stubGlobal("PublicKeyCredential", class {});
    vi.stubGlobal("AuthenticatorAttestationResponse", TestAttestationResponse);
    vi.stubGlobal("AuthenticatorAssertionResponse", class {});
    vi.stubGlobal("navigator", { credentials: { create }, platform: "Win32" });

    const calls: Array<[string, RequestInit | undefined]> = [];
    const api = vi.fn(async (path: string, options?: RequestInit) => {
      calls.push([path, options]);
      if (path === "/account/passkeys/options") {
        return {
          ok: true,
          options: {
            challenge: "AQID",
            rp: { id: "127.0.0.1", name: "Development RP" },
            user: { id: "BAUG", name: "user", displayName: "User" },
            pubKeyCredParams: [{ type: "public-key", alg: -7 }],
            excludeCredentials: [],
          },
        };
      }
      return { ok: true };
    });

    await registerPasskey(api as unknown as ApiClient["api"], "/minishop");

    expect(create).toHaveBeenCalledOnce();
    const registerCall = calls.find(([path]) => path === "/account/passkeys/register");
    expect(registerCall).toBeDefined();
    expect(JSON.parse(String(registerCall?.[1]?.body))).toMatchObject({
      challenge: "AQID",
      name: "/minishop · Windows",
      credential: {
        id: "credential-id",
        response: { transports: ["internal"] },
      },
    });
  });
});

describe("loginWithPasskey", () => {
  it("clears a previous manual logout before opening the authenticated app", async () => {
    class TestAssertionResponse {
      clientDataJSON = Uint8Array.from([1, 2]).buffer;
      authenticatorData = Uint8Array.from([3, 4]).buffer;
      signature = Uint8Array.from([5, 6]).buffer;
      userHandle = null;
    }

    const assign = vi.fn();
    const removeItem = vi.fn();
    const credential = {
      id: "credential-id",
      rawId: Uint8Array.from([7, 8]).buffer,
      type: "public-key",
      authenticatorAttachment: "platform",
      getClientExtensionResults: () => ({}),
      response: new TestAssertionResponse(),
    };
    const get = vi.fn().mockResolvedValue(credential);
    const fetch = vi
      .fn()
      .mockResolvedValueOnce({
        json: async () => ({
          ok: true,
          options: {
            challenge: "AQID",
            rpId: "example.test",
            allowCredentials: [{ id: "BAUG", type: "public-key" }],
          },
        }),
      })
      .mockResolvedValueOnce({ json: async () => ({ ok: true }) });

    vi.stubGlobal("window", { PublicKeyCredential: class {}, location: { assign } });
    vi.stubGlobal("PublicKeyCredential", class {});
    vi.stubGlobal("AuthenticatorAttestationResponse", class {});
    vi.stubGlobal("AuthenticatorAssertionResponse", TestAssertionResponse);
    vi.stubGlobal("navigator", { credentials: { get } });
    vi.stubGlobal("localStorage", { removeItem });
    vi.stubGlobal("fetch", fetch);

    await loginWithPasskey("/api");

    expect(removeItem).toHaveBeenCalledWith("rw_webapp_manual_logout");
    expect(assign).toHaveBeenCalledWith("/home");
  });
});
