import { afterEach, describe, expect, it, vi } from "vitest";

import { buildApiUrl, createApiClient } from "./publicApi";

function jsonResponse(payload = {}, status = 200) {
  return {
    status,
    json: vi.fn(async () => payload),
  };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("createApiClient", () => {
  it("builds same-origin API URLs without duplicating the /api prefix", () => {
    expect(buildApiUrl("/me")).toBe("/api/me");
    expect(buildApiUrl("/api/me")).toBe("/api/me");
    expect(buildApiUrl("/bootstrap?i18n_scope=webapp")).toBe("/api/bootstrap?i18n_scope=webapp");
  });

  it("adds the in-memory session token to authenticated API requests", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const client = createApiClient({
      getAuthToken: () => "session-token",
    });

    await client.api("/me");

    const fetchCalls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    const requestOptions = fetchCalls[0][1];
    expect(requestOptions.credentials).toBe("same-origin");
    expect((requestOptions.headers as Headers).get("Authorization")).toBe("Bearer session-token");
  });

  it("aborts stalled authenticated API requests", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(
      (_url, options) =>
        new Promise((_resolve, reject) => {
          options.signal.addEventListener("abort", () => {
            reject(options.signal.reason);
          });
        })
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = createApiClient({ requestTimeoutMs: 25 });
    const request = client.api("/me");
    const rejection = expect(request).rejects.toMatchObject({ name: "TimeoutError" });

    await vi.advanceTimersByTimeAsync(25);
    await rejection;
  });
});
