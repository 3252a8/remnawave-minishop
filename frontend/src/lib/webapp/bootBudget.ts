let activeController: AbortController | null = null;

export const WEBAPP_BOOT_BUDGET_MS = 20000;

export function beginBootBudget(): AbortController {
  activeController?.abort();
  const controller = new AbortController();
  activeController = controller;
  return controller;
}

export function currentBootSignal(): AbortSignal | undefined {
  return activeController?.signal;
}

export function finishBootBudget(controller: AbortController): void {
  if (activeController === controller) activeController = null;
}

export function recordClientTiming(
  stage: string,
  started: number,
  outcome: string,
  requestId?: string
): void {
  if (typeof performance === "undefined") return;
  try {
    const name = `minishop.${stage}`;
    performance.clearMeasures(name);
    performance.measure(name, {
      start: started,
      end: performance.now(),
      detail: { outcome, requestId },
    });
  } catch {
    // Older embedded browsers can still load the app without User Timing Level 3.
  }
}

export function isInvalidSession(error: unknown): boolean {
  if (error && typeof error === "object" && "status" in error && error.status === 401) return true;
  const message = error instanceof Error ? error.message : String(error || "");
  return [
    "unauthorized",
    "auth_required",
    "invalid_token",
    "session_expired",
    "access_denied",
  ].includes(message);
}
