import { currentBootSignal, recordClientTiming } from "./bootBudget";
import { requestSignal } from "./requestSignal";

export async function fetchApiJson(
  url: string,
  path: string,
  options: RequestInit,
  requestTimeoutMs: number,
  onUnauthorized: () => void
): Promise<Record<string, unknown>> {
  const { signal, cleanup } = requestSignal(
    options.signal || currentBootSignal(),
    requestTimeoutMs
  );
  const started = performance.now();
  let outcome = "failed";
  let requestId: string | undefined;
  try {
    const response = await fetch(url, {
      // The Telegram Mini App WebView keeps its HTTP cache across openings,
      // so a GET answered from it can show settings the server no longer
      // serves. The server says no-store too; this covers the leg where a
      // proxy drops the header.
      cache: "no-store",
      ...options,
      credentials: "same-origin",
      signal,
    });
    const payload = await response.json().catch(() => ({}));
    requestId = response.headers?.get("X-Request-ID") || undefined;
    if (signal?.aborted) throw new DOMException("request_cancelled", "AbortError");
    outcome = String(response.status);
    if (response.status >= 500 || response.status === 429) {
      throw Object.assign(new Error("service_unavailable"), {
        status: response.status,
        payload,
      });
    }
    if (response.status === 401) onUnauthorized();
    return payload as Record<string, unknown>;
  } finally {
    recordClientTiming(
      path.startsWith("/auth/") ? "auth" : path.split("?")[0] === "/me" ? "profile" : "api",
      started,
      signal?.aborted ? "cancelled" : outcome,
      requestId
    );
    cleanup();
  }
}
