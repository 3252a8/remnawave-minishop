import { adminErrorMessage } from "../errors.js";
import {
  buildAdminLogsPath,
  unwrap,
  type ApiResponse,
  type ApiClient,
  type GetResponse,
} from "../../webapp/publicApi";
import type { components } from "../../api/openapi.generated";
import { createAdminPerfSpan } from "../adminPerfMarks";
import { fetchAdminQuery, type AdminQueryClient, type AdminQueryKey } from "./adminQueryCache";
import { defineRawStateProperty } from "./rawStateProperty";

const LOGS_QUERY_KEY = ["admin", "logs"] as const;
const LOGS_PAGE_SIZE = 50;

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = <Path extends Parameters<ApiClient["api"]>[0]>(
  path: Path,
  options?: Parameters<ApiClient["api"]>[1]
) => Promise<ApiResponse<Path> | AdminErrorResponse>;
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type LogEntry = components["schemas"]["LogOut"];
type LogsResponse = GetResponse<"/api/admin/logs">;
type LogsQueryKey = readonly [string, string, { page: number; filter: string }];
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
  queryClient?: AdminQueryClient | null;
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
  let logs = $state.raw<LogEntry[]>([]);
  const state = $state<Omit<LogsState, "logs">>({
    logsTotal: 0,
    logsPage: 0,
    logsUserFilter: "",
    logsLoading: false,
    logsError: "",
  });
  const store = Object.create(state) as LogsStore;
  defineRawStateProperty(store, "logs", {
    get: () => logs,
    set: (value) => {
      logs = value;
    },
  });

  let requestSeq = 0;

  function logsQueryKey(page: number, filter: string): LogsQueryKey {
    return [LOGS_QUERY_KEY[0], LOGS_QUERY_KEY[1], { page, filter }];
  }

  function logsPath(page: number, filter: string): ReturnType<typeof buildAdminLogsPath> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(LOGS_PAGE_SIZE),
    });
    if (filter) {
      params.set("user_id", filter);
    }
    return buildAdminLogsPath(params);
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
    return fetchAdminQuery({
      queryClient,
      queryKey: logsQueryKey(page, filter) satisfies AdminQueryKey,
      queryFn: () => requestLogs(page, filter),
      refresh,
    });
  }

  async function loadLogs({ refresh = false }: { refresh?: boolean } = {}): Promise<void> {
    const seq = ++requestSeq;
    const perf = createAdminPerfSpan("logs");
    state.logsLoading = true;
    const currentPage = state.logsPage;
    const filter = state.logsUserFilter.trim();

    try {
      const data = await queryLogs(currentPage, filter, refresh);
      perf.apiResponse();
      if (seq === requestSeq) {
        logs = data.logs || [];
        state.logsTotal = data.total || 0;
        state.logsError = "";
        perf.stateAssign();
        void perf.renderSettled();
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

  return Object.assign(store, {
    loadLogs,
    setPage,
    setFilter,
  });
}
