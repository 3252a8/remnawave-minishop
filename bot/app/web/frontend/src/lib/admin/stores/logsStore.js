import { writable } from "svelte/store";

export function createLogsStore({ api }) {
  const state = writable({
    logs: [],
    logsTotal: 0,
    logsPage: 0,
    logsUserFilter: "",
    logsLoading: false,
  });

  const LOGS_PAGE_SIZE = 50;

  async function loadLogs() {
    state.update((s) => ({ ...s, logsLoading: true }));
    let currentPage = 0;
    let filter = "";
    state.update((s) => {
      currentPage = s.logsPage;
      filter = s.logsUserFilter;
      return s;
    });

    try {
      let q = `/admin/logs?page=${currentPage}&page_size=${LOGS_PAGE_SIZE}`;
      if (filter.trim()) {
        q += `&user_id=${encodeURIComponent(filter.trim())}`;
      }
      const data = await api(q);
      if (data?.ok) {
        state.update((s) => ({
          ...s,
          logs: data.logs || [],
          logsTotal: data.total || 0,
        }));
      }
    } finally {
      state.update((s) => ({ ...s, logsLoading: false }));
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
