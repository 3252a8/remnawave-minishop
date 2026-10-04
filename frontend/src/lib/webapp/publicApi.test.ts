import { afterEach, describe, expect, it, vi } from "vitest";

import { buildAdminInformationPagesPath, buildApiUrl, createApiClient } from "./publicApi";

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

  it("keeps the information-page route in the typed admin API query", () => {
    expect(buildAdminInformationPagesPath("/company/about")).toBe(
      "/admin/information-pages?path=%2Fcompany%2Fabout"
    );
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

  it("forwards only a valid private tariff access code", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    let accessCode = "AB".repeat(16);
    const client = createApiClient({ getTariffAccessCode: () => accessCode });

    await client.api("/me");
    accessCode = "invalid";
    await client.api("/me");

    const fetchCalls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect((fetchCalls[0][1].headers as Headers).get("X-Tariff-Access-Code")).toBe("ab".repeat(16));
    expect((fetchCalls[1][1].headers as Headers).has("X-Tariff-Access-Code")).toBe(false);
  });

  it("loads protected payment exports with the in-memory session token", async () => {
    const body = new Blob(["payment_id"], { type: "text/csv" });
    const fetchMock = vi.fn(async () => ({
      status: 200,
      ok: true,
      blob: vi.fn(async () => body),
      json: vi.fn(async () => ({})),
    }));
    vi.stubGlobal("fetch", fetchMock);

    const client = createApiClient({ getAuthToken: () => "session-token" });
    await expect(client.apiBlob("/admin/payments/export.csv")).resolves.toBe(body);

    const fetchCalls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(fetchCalls[0][0]).toBe("/api/admin/payments/export.csv");
    expect(fetchCalls[0][1].credentials).toBe("same-origin");
    expect((fetchCalls[0][1].headers as Headers).get("Authorization")).toBe("Bearer session-token");
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

function emojiResponse(blob = new Blob(["preview"], { type: "image/png" }), status = 200) {
  return {
    status,
    ok: status >= 200 && status < 300,
    blob: vi.fn(async () => blob),
    json: vi.fn(async () => ({ ok: false, error: "offline" })),
  };
}

describe("authenticated emoji media cache", () => {
  const path = "/admin/telegram-emoji/media/5368324170671202286";

  it("shares concurrent requests and reuses a warm Blob when the picker reopens", async () => {
    const response = emojiResponse();
    const fetchMock = vi.fn(async () => response);
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient({ getAuthToken: () => "session-a" });
    const [first, second] = await Promise.all([
      client.apiBlob(path),
      client.apiBlob(`/api${path}`),
    ]);
    expect(first).toBe(second);
    expect(await client.apiBlob(path)).toBe(first);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls[0][1].cache).toBe("default");
    expect(calls[0][1].credentials).toBe("same-origin");
    expect((calls[0][1].headers as Headers).get("Authorization")).toBe("Bearer session-a");
  });

  it("cancels one waiter without aborting the shared request for another", async () => {
    let complete: ((response: ReturnType<typeof emojiResponse>) => void) | undefined;
    const fetchMock = vi.fn(
      (_url: string, _options: RequestInit) =>
        new Promise((resolve) => {
          complete = resolve;
        })
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient({ getCsrfToken: () => "cookie-session-a" });
    const controller = new AbortController();
    const first = client.apiBlob(path, { signal: controller.signal });
    const rejected = expect(first).rejects.toMatchObject({ name: "AbortError" });
    const second = client.apiBlob(path);
    await Promise.resolve();
    controller.abort();
    await rejected;
    expect(fetchMock.mock.calls[0][1].signal?.aborted).toBe(false);
    complete?.(emojiResponse());
    const blob = await second;
    expect(await client.apiBlob(path)).toBe(blob);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("continues warming after every waiter closes and rejects pre-aborted consumers", async () => {
    let complete: ((response: ReturnType<typeof emojiResponse>) => void) | undefined;
    const fetchMock = vi.fn(
      (_url: string, _options: RequestInit) =>
        new Promise((resolve) => {
          complete = resolve;
        })
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient({ getAuthToken: () => "session-a" });
    const controller = new AbortController();
    const closed = client.apiBlob(path, { signal: controller.signal });
    const rejected = expect(closed).rejects.toMatchObject({ name: "AbortError" });
    await Promise.resolve();
    controller.abort();
    await rejected;
    complete?.(emojiResponse());
    await client.apiBlob(path);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await expect(
      client.apiBlob(`${path}?v=0000000000000001`, { signal: controller.signal })
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("isolates bearer/CSRF changes, explicit auth headers and full URL versions", async () => {
    const fetchMock = vi.fn(async () => emojiResponse());
    vi.stubGlobal("fetch", fetchMock);
    let token = "session-a";
    let csrf = "csrf-a";
    const client = createApiClient({ getAuthToken: () => token, getCsrfToken: () => csrf });
    await client.apiBlob(`${path}?v=0000000000000001`);
    await client.apiBlob(`${path}?v=0000000000000001`);
    csrf = "csrf-b";
    await client.apiBlob(`${path}?v=0000000000000001`);
    token = "session-b";
    await client.apiBlob(`${path}?v=0000000000000001`);
    await client.apiBlob(`${path}?v=0000000000000001`, {
      headers: { Authorization: "Bearer explicit-session" },
    });
    await client.apiBlob(`${path}?v=0000000000000002`);
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });

  it("scopes cookie-only sessions through the current CSRF cookie", async () => {
    const cookieDocument = { cookie: "rw_webapp_csrf=cookie-a" };
    vi.stubGlobal("document", cookieDocument);
    const fetchMock = vi.fn(async () => emojiResponse());
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient();
    await client.apiBlob(path);
    await client.apiBlob(path);
    cookieDocument.cookie = "rw_webapp_csrf=cookie-b";
    await client.apiBlob(path);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    cookieDocument.cookie = "";
    await client.apiBlob(path);
    await client.apiBlob(path);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("expires nonversioned previews after five minutes and versioned ones after a day", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(async () => emojiResponse());
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient({ getAuthToken: () => "session-a" });
    await client.apiBlob(path);
    await client.apiBlob(`${path}?v=0123456789abcdef`);
    await vi.advanceTimersByTimeAsync(300000);
    await client.apiBlob(path);
    await client.apiBlob(`${path}?v=0123456789abcdef`);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(86400000 - 300000);
    await client.apiBlob(`${path}?v=0123456789abcdef`);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("retries failed media and leaves exports/ordinary attachments uncached", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(emojiResponse(undefined, 503))
      .mockImplementation(async () => emojiResponse());
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient({ getAuthToken: () => "session-a" });
    await expect(client.apiBlob(path)).rejects.toMatchObject({ error: "offline" });
    await client.apiBlob(path);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    for (const otherPath of ["/admin/payments/export.csv", "/support/images/7"]) {
      await client.apiBlob(otherPath);
      await client.apiBlob(otherPath);
    }
    expect(fetchMock).toHaveBeenCalledTimes(6);
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls.slice(2).every(([, options]) => options.cache === "no-store")).toBe(true);
  });

  it("still times out a shared fetch and permits the next retry", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(
      (_url: string, options: RequestInit) =>
        new Promise((_resolve, reject) => {
          options.signal?.addEventListener("abort", () => reject(options.signal?.reason));
        })
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient({ getAuthToken: () => "session-a", requestTimeoutMs: 25 });
    const first = expect(client.apiBlob(path)).rejects.toMatchObject({ name: "TimeoutError" });
    const second = expect(client.apiBlob(path)).rejects.toMatchObject({ name: "TimeoutError" });
    await vi.advanceTimersByTimeAsync(25);
    await Promise.all([first, second]);
    fetchMock.mockImplementation(async () => emojiResponse());
    await client.apiBlob(path);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
