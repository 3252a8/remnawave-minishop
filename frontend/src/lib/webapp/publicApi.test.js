import { afterEach, describe, expect, it, vi } from "vitest";

import { createApiClient } from "./publicApi";

function jsonResponse(payload = {}, status = 200) {
  return {
    status,
    json: vi.fn(async () => payload),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("createApiClient", () => {
  it("adds the in-memory session token to authenticated API requests", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const client = createApiClient({
      getAuthToken: () => "session-token",
    });

    await client.api("/me");

    const requestOptions = fetchMock.mock.calls[0][1];
    expect(requestOptions.credentials).toBe("same-origin");
    expect(requestOptions.headers.get("Authorization")).toBe("Bearer session-token");
  });
});
