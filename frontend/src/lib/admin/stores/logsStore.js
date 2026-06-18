import { writable } from "svelte/store";

const LOGS_QUERY_KEY = ["admin", "logs"];
const LOGS_STALE_MS = 30 * 1000;

export function createLogsStore({ api, queryClient = null }) {
  const state = writable({
    logs: [],
    logsTotal: 0,
    logsPage: 0,
    logsUserFilter: "",
    logsLoading: false,
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
      const error = new Error("load_failed");
      error.payload = data;
      throw error;
    }
    return data;
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
        }));
      }
    } catch {
      // Logs had no visible error state before the query pilot; keep that UI
      // contract and leave the previous page data in place on failures.
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
