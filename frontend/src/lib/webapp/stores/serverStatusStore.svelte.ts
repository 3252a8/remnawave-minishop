import type { components } from "../../api/openapi.generated";
import { buildServerStatusPath, unwrap, type ApiClient } from "../publicApi";

export type ServerStatusData = components["schemas"]["ServerStatus"];
export type ServerStatusProvider = components["schemas"]["StatusProvider"];
export type ServerStatusHistoryEntry = Pick<
  components["schemas"]["StatusItem"],
  "status" | "latencyMs" | "lastCheck"
>;
export type ServerStatusStore = {
  data: ServerStatusData | null;
  history: Record<string, ServerStatusHistoryEntry[]>;
  error: boolean;
  loading: boolean;
  refreshing: boolean;
  refresh: (force?: boolean) => Promise<ServerStatusData | null>;
  start: () => void;
  stop: () => void;
};

const POLL_INTERVAL_MS = 60_000;
const HISTORY_SIZE = 5;

export function statusProvider(data: ServerStatusData | null): ServerStatusProvider | null {
  const sourceProvider = data?.sources?.[0]?.provider;
  if (sourceProvider) return sourceProvider;
  return data?.enabled && data.externalUrl ? "url" : null;
}

export function shouldPollServerStatus(data: ServerStatusData | null): boolean {
  const provider = statusProvider(data);
  return Boolean(data?.enabled && (provider === "uptime-kuma" || provider === "xray-checker"));
}

export function createServerStatusStore(
  api: ApiClient["api"],
  pollIntervalMs = POLL_INTERVAL_MS
): ServerStatusStore {
  const state = $state<ServerStatusStore>({
    data: null,
    history: {},
    error: false,
    loading: false,
    refreshing: false,
    refresh,
    start,
    stop,
  });
  let active = false;
  let visible = true;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let inFlight: Promise<ServerStatusData | null> | null = null;
  let listening = false;

  function clearTimer(): void {
    if (timer) clearTimeout(timer);
    timer = null;
  }

  function schedule(): void {
    clearTimer();
    if (!active || !visible || !shouldPollServerStatus(state.data)) return;
    timer = setTimeout(() => {
      timer = null;
      void refresh(true);
    }, pollIntervalMs);
  }

  async function refresh(force = false): Promise<ServerStatusData | null> {
    if (inFlight) return inFlight;
    if (!force && state.data) return state.data;
    state.loading = !state.data;
    state.refreshing = Boolean(state.data);
    inFlight = (async () => {
      try {
        const response = await api(buildServerStatusPath());
        const data = unwrap(response);
        recordHistory(data);
        state.data = data;
        state.error = false;
        return data;
      } catch {
        state.error = true;
        return state.data;
      } finally {
        state.loading = false;
        state.refreshing = false;
        inFlight = null;
        schedule();
      }
    })();
    return inFlight;
  }

  function recordHistory(data: ServerStatusData): void {
    if (state.data && data.updatedAt === state.data.updatedAt) return;
    const nextHistory: Record<string, ServerStatusHistoryEntry[]> = {};
    for (const group of data.groups || []) {
      for (const item of group.items) {
        const previous = state.history[item.id] || [];
        nextHistory[item.id] = [
          ...previous,
          { status: item.status, latencyMs: item.latencyMs, lastCheck: item.lastCheck },
        ].slice(-HISTORY_SIZE);
      }
    }
    state.history = nextHistory;
  }

  function handleVisibilityChange(): void {
    visible = typeof document === "undefined" || document.visibilityState !== "hidden";
    if (!visible) {
      clearTimer();
      return;
    }
    if (active && shouldPollServerStatus(state.data)) void refresh(true);
  }

  function start(): void {
    active = true;
    visible = typeof document === "undefined" || document.visibilityState !== "hidden";
    if (typeof document !== "undefined" && !listening) {
      document.addEventListener("visibilitychange", handleVisibilityChange);
      listening = true;
    }
    if (visible) void refresh(shouldPollServerStatus(state.data));
  }

  function stop(): void {
    active = false;
    clearTimer();
    if (typeof document !== "undefined" && listening) {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      listening = false;
    }
  }

  return state;
}
