import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApiClient } from "./publicApi.js";
import { registerPasskey, suggestedPasskeyName } from "./passkeys.js";

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
