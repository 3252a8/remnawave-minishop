function apiTimeoutError(): Error {
  const error = new Error("api_request_timeout");
  error.name = "TimeoutError";
  return error;
}

export function requestSignal(
  existingSignal: AbortSignal | null | undefined,
  timeoutMs: number
): { signal: AbortSignal | undefined; cleanup: () => void } {
  const timeout = Math.max(0, Number(timeoutMs || 0));
  if (timeout <= 0 || typeof AbortController === "undefined") {
    return { signal: existingSignal || undefined, cleanup: () => {} };
  }

  const controller = new AbortController();
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  const abortFromExisting = () => controller.abort(existingSignal?.reason);

  if (existingSignal?.aborted) {
    controller.abort(existingSignal.reason);
  } else {
    existingSignal?.addEventListener("abort", abortFromExisting, { once: true });
  }

  timeoutId = setTimeout(() => {
    if (!controller.signal.aborted) controller.abort(apiTimeoutError());
  }, timeout);

  return {
    signal: controller.signal,
    cleanup: () => {
      if (timeoutId) clearTimeout(timeoutId);
      existingSignal?.removeEventListener("abort", abortFromExisting);
    },
  };
}
