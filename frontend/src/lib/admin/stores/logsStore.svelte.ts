import { adminErrorMessage } from "../errors.js";
import { unwrap, type ApiResponse, type GetResponse } from "../../webapp/publicApi";
import type { components } from "../../api/openapi.generated";

const LOGS_QUERY_KEY = ["admin", "logs"] as const;
const LOGS_STALE_MS = 30 * 1000;
const LOGS_PAGE_SIZE = 50;

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = <Path extends string>(
  path: Path,
  options?: RequestInit
) => Promise<ApiResponse<Path> | AdminErrorResponse>;
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type LogEntry = components["schemas"]["LogOut"];
type LogsResponse = GetResponse<"/api/admin/logs">;
type LogsQueryKey = readonly [string, string, { page: number; filter: string }];
type LogsQueryClient = {
  invalidateQueries: (options: { queryKey: LogsQueryKey }) => Promise<unknown>;
  fetchQuery: (options: {
    queryKey: LogsQueryKey;
    queryFn: () => Promise<LogsResponse>;
    retry: false;
    staleTime: number;
  }) => Promise<LogsResponse>;
};
type LogsState = {
  logs: LogEntry[];
  logsTotal: number;
  logsPage: number;
  logsUserFilter: string;
  logsLoading: boolean;
  logsError: string;
};
type LogsStoreOptions = {
  api: AdminApi;
  at?: TranslateFn;
  onToast?: ToastFn;
  queryClient?: LogsQueryClient | null;
};
export type LogsStore = LogsState & {
  loadLogs: (options?: { refresh?: boolean }) => Promise<void>;
  setPage: (page: number) => void;
  setFilter: (filter: string) => void;
};

class AdminLogsError extends Error {
  payload: AdminErrorResponse;

  constructor(message: string, payload: AdminErrorResponse) {
    super(message);
    this.payload = payload;
  }
}

function isOkResponse<T extends { ok: true }>(response: T | AdminErrorResponse): response is T {
  return response.ok === true;
}

export function createLogsStore({
  api,
  at = (key, _params, fallback) => fallback || key,
  onToast = () => {},
  queryClient = null,
}: LogsStoreOptions): LogsStore {
  const state = $state<LogsState>({
    logs: [],
    logsTotal: 0,
    logsPage: 0,
    logsUserFilter: "",
    logsLoading: false,
    logsError: "",
  });

  let requestSeq = 0;

  function logsQueryKey(page: number, filter: string): LogsQueryKey {
    return [LOGS_QUERY_KEY[0], LOGS_QUERY_KEY[1], { page, filter }];
  }

  function logsPath(page: number, filter: string): string {
    let q = `/admin/logs?page=${page}&page_size=${LOGS_PAGE_SIZE}`;
    if (filter) {
      q += `&user_id=${encodeURIComponent(filter)}`;
    }
    return q;
  }

  async function requestLogs(page: number, filter: string): Promise<LogsResponse> {
    const data = (await api(logsPath(page, filter))) as LogsResponse | AdminErrorResponse;
    if (!isOkResponse(data)) {
      throw new AdminLogsError(adminErrorMessage(data, at, "load_failed"), data);
    }
    return unwrap(data);
  }

  function loadErrorMessage(error: unknown): string {
    if (error instanceof AdminLogsError) return adminErrorMessage(error.payload, at, "load_failed");
    if (error instanceof Error) return error.message;
    return String(error || "load_failed");
  }

  async function queryLogs(page: number, filter: string, refresh: boolean): Promise<LogsResponse> {
    if (!queryClient) return requestLogs(page, filter);
    const queryKey = logsQueryKey(page, filter);
    if (refresh) await queryClient.invalidateQueries({ queryKey });
    return queryClient.fetchQuery({
      queryKey,
      queryFn: () => requestLogs(page, filter),
      retry: false,
      staleTime: LOGS_STALE_MS,
    });
  }

  async function loadLogs({ refresh = false }: { refresh?: boolean } = {}): Promise<void> {
    const seq = ++requestSeq;
    state.logsLoading = true;
    const currentPage = state.logsPage;
    const filter = state.logsUserFilter.trim();

    try {
      const data = await queryLogs(currentPage, filter, refresh);
      if (seq === requestSeq) {
        state.logs = data.logs || [];
        state.logsTotal = data.total || 0;
        state.logsError = "";
      }
    } catch (error) {
      const message = loadErrorMessage(error);
      if (seq === requestSeq) {
        state.logsError = message;
      }
      if (message) onToast(message);
    } finally {
      if (seq === requestSeq) {
        state.logsLoading = false;
      }
    }
  }

  function setPage(page: number): void {
    state.logsPage = page;
    void loadLogs();
  }

  function setFilter(filter: string): void {
    state.logsUserFilter = filter;
  }

  return Object.assign(state, {
    loadLogs,
    setPage,
    setFilter,
  });
}
