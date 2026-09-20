import { describe, expect, it } from "vitest";
import { loginProviderCallbackUrl, loginProviderOrigin } from "./loginProviderSetup";

describe("login provider setup URLs", () => {
  it("uses only the public origin even when the Mini App URL contains a path", () => {
    expect(loginProviderOrigin("https://app.example.com/minishop/", "https://admin.local")).toBe(
      "https://app.example.com"
    );
    expect(
      loginProviderCallbackUrl("google", "https://app.example.com/minishop/", "https://admin.local")
    ).toBe("https://app.example.com/auth/google/callback");
    expect(
      loginProviderCallbackUrl(
        "discord",
        "https://app.example.com/minishop/",
        "https://admin.local"
      )
    ).toBe("https://app.example.com/auth/discord/callback");
  });

  it("falls back to the current origin when the configured URL is missing or invalid", () => {
    expect(loginProviderCallbackUrl("yandex", "", "http://127.0.0.1:8082/")).toBe(
      "http://127.0.0.1:8082/auth/yandex/callback"
    );
    expect(loginProviderCallbackUrl("google", "not a url", "https://app.example.com")).toBe(
      "https://app.example.com/auth/google/callback"
    );
  });
});
