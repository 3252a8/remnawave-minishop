import { writable } from "svelte/store";
import { adminErrorMessage } from "../errors.js";

const LOGS_QUERY_KEY = ["admin", "logs"];
const LOGS_STALE_MS = 30 * 1000;

export function createLogsStore({
  api,
  at = (key, _params, fallback) => fallback || key,
  onToast = () => {},
  queryClient = null,
}) {
  const state = writable({
    logs: [],
    logsTotal: 0,
    logsPage: 0,
    logsUserFilter: "",
    logsLoading: false,
    logsError: "",
  });

  const LOGS_PAGE_SIZE = 50;
  let requestSeq = 0;

  function logsQueryKey(page, filter) {
    return [...LOGS_QUERY_KEY, { page, filter }];
  }

  function logsPath(page, filter) {
    let q = `/admin/logs?page=${page}&page_size=${LOGS_PAGE_SIZE}`;
    if (filter) {
      q += `&user_id=${encodeURIComponent(filter)}`;
    }
    return q;
  }

  async function requestLogs(page, filter) {
    const data = await api(logsPath(page, filter));
    if (!data?.ok) {
      const error = new Error(adminErrorMessage(data, at, "load_failed"));
      error.payload = data;
      throw error;
    }
    return data;
  }

  function loadErrorMessage(error) {
    if (error?.payload) return adminErrorMessage(error.payload, at, "load_failed");
    return error?.message || String(error || "load_failed");
  }

  async function queryLogs(page, filter, refresh) {
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

  async function loadLogs({ refresh = false } = {}) {
    const seq = ++requestSeq;
    state.update((s) => ({ ...s, logsLoading: true }));
    let currentPage = 0;
    let filter = "";
    state.update((s) => {
      currentPage = s.logsPage;
      filter = s.logsUserFilter;
      return s;
    });
    filter = filter.trim();

    try {
      const data = await queryLogs(currentPage, filter, refresh);
      if (seq === requestSeq) {
        state.update((s) => ({
          ...s,
          logs: data.logs || [],
          logsTotal: data.total || 0,
          logsError: "",
        }));
      }
    } catch (error) {
      const message = loadErrorMessage(error);
      if (seq === requestSeq) {
        state.update((s) => ({ ...s, logsError: message }));
      }
      if (message) onToast(message);
    } finally {
      if (seq === requestSeq) {
        state.update((s) => ({ ...s, logsLoading: false }));
      }
    }
  }

  function setPage(page) {
    state.update((s) => ({ ...s, logsPage: page }));
    loadLogs();
  }

  function setFilter(filter) {
    state.update((s) => ({ ...s, logsUserFilter: filter }));
  }

  return {
    subscribe: state.subscribe,
    set: state.set,
    update: state.update,
    loadLogs,
    setPage,
    setFilter,
  };
}
