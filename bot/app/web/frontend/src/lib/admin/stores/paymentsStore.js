import { writable } from "svelte/store";

export function createPaymentsStore({ api }) {
  const state = writable({
    payments: [],
    paymentsTotal: 0,
    paymentsPage: 0,
    paymentsLoading: false,
  });

  const PAYMENTS_PAGE_SIZE = 25;

  async function loadPayments() {
    state.update((s) => ({ ...s, paymentsLoading: true }));
    let currentPage = 0;
    state.update((s) => {
      currentPage = s.paymentsPage;
      return s;
    });

    try {
      const data = await api(`/admin/payments?page=${currentPage}&page_size=${PAYMENTS_PAGE_SIZE}`);
      if (data?.ok) {
        state.update((s) => ({
          ...s,
          payments: data.payments || [],
          paymentsTotal: data.total || 0,
        }));
      }
    } finally {
      state.update((s) => ({ ...s, paymentsLoading: false }));
    }
  }

  function setPage(page) {
    state.update((s) => ({ ...s, paymentsPage: page }));
    loadPayments();
  }

  return {
    subscribe: state.subscribe,
    set: state.set,
    update: state.update,
    loadPayments,
    setPage,
  };
}
