import { writable } from "svelte/store";

export function createAdminSupportStore({ api, onToast, at }) {
  const state = writable({
    tickets: [],
    stats: { active: 0, closed: 0, open: 0, awaiting_admin: 0, total_unread_admin: 0 },
    filters: {
      status: "active",
      priority: "",
      category: "",
      search: "",
      sort: "importance_desc",
    },
    loading: false,
    openedTicketId: null,
    openedTicket: null,
    messages: [],
    userSnapshot: null,
    detailLoading: false,
    sending: false,
    composerInternalNote: false,
  });

  let pollTimer = null;
  let active = "stats";

  function setActive(section) {
    active = section;
  }

  function pushTicketPath(ticketId) {
    if (typeof window === "undefined" || window.location.protocol === "file:") return;
    if (active !== "support") return;
    const target = ticketId ? `/admin/support/${ticketId}` : "/admin/support";
    if (window.location.pathname !== target) {
      window.history.pushState(
        null,
        "",
        `${target}${window.location.search}${window.location.hash}`
      );
    }
  }

  async function loadStats() {
    const res = await api("/admin/support/stats");
    if (res?.ok) state.update((s) => ({ ...s, stats: res.stats || s.stats }));
  }

  async function loadList() {
    state.update((s) => ({ ...s, loading: true }));
    let filters;
    state.update((s) => {
      filters = s.filters;
      return s;
    });
    try {
      const params = new URLSearchParams({ limit: "50", offset: "0" });
      for (const [key, value] of Object.entries(filters || {})) {
        if (value) params.set(key, value);
      }
      const res = await api(`/admin/support/tickets?${params.toString()}`);
      if (res?.ok) state.update((s) => ({ ...s, tickets: res.tickets || [] }));
      else if (res?.error) onToast(res.message || res.error);
    } finally {
      state.update((s) => ({ ...s, loading: false }));
    }
  }

  async function openTicket(ticketId, opts = {}) {
    const id = Number(ticketId);
    if (!id) return;
    state.update((s) => ({
      ...s,
      openedTicketId: id,
      openedTicket: s.openedTicket?.ticket_id === id ? s.openedTicket : null,
      messages: s.openedTicket?.ticket_id === id ? s.messages : [],
      userSnapshot: s.openedTicket?.ticket_id === id ? s.userSnapshot : null,
      detailLoading: true,
    }));
    if (!opts.skipPush) pushTicketPath(id);
    try {
      const res = await api(`/admin/support/tickets/${id}`);
      if (res?.ok) {
        state.update((s) => ({
          ...s,
          openedTicket: res.ticket,
          messages: res.messages || [],
          userSnapshot: res.user_snapshot || null,
        }));
        await api(`/admin/support/tickets/${id}/read`, { method: "POST", body: "{}" });
        await loadStats();
      } else onToast(res?.message || res?.error || "not_found");
    } finally {
      state.update((s) => ({ ...s, detailLoading: false }));
    }
  }

  function closeTicketView(opts = {}) {
    state.update((s) => ({
      ...s,
      openedTicketId: null,
      openedTicket: null,
      messages: [],
      userSnapshot: null,
    }));
    if (!opts.skipPush) pushTicketPath(null);
  }

  async function sendReply(body) {
    let current;
    let internal;
    state.update((s) => {
      current = s.openedTicketId;
      internal = s.composerInternalNote;
      return { ...s, sending: true };
    });
    if (!current) return;
    try {
      const res = await api(`/admin/support/tickets/${current}/messages`, {
        method: "POST",
        body: JSON.stringify({ body, is_internal_note: internal }),
      });
      if (!res?.ok) throw res;
      state.update((s) => ({
        ...s,
        openedTicket: res.ticket
          ? { ...s.openedTicket, ...res.ticket, user: res.ticket.user || s.openedTicket?.user }
          : s.openedTicket,
        messages: [...s.messages, res.message],
      }));
      await loadList();
      await loadStats();
    } catch (error) {
      onToast(error?.message || at("support_send_failed", {}, "Send failed"));
    } finally {
      state.update((s) => ({ ...s, sending: false }));
    }
  }

  async function patchTicket(updates) {
    let current;
    state.update((s) => {
      current = s.openedTicketId;
      return s;
    });
    if (!current) return;
    const res = await api(`/admin/support/tickets/${current}`, {
      method: "PATCH",
      body: JSON.stringify(updates),
    });
    if (res?.ok) {
      state.update((s) => ({
        ...s,
        openedTicket: res.ticket
          ? { ...s.openedTicket, ...res.ticket, user: res.ticket.user || s.openedTicket?.user }
          : s.openedTicket,
      }));
      await loadList();
      await loadStats();
    } else onToast(res?.message || res?.error || "update_failed");
  }

  function closeTicket() {
    patchTicket({ status: "closed" });
  }

  function toggleInternalNote() {
    state.update((s) => ({ ...s, composerInternalNote: !s.composerInternalNote }));
  }

  function setFilter(key, value) {
    state.update((s) => ({ ...s, filters: { ...s.filters, [key]: value } }));
  }

  function setStatusView(status) {
    state.update((s) => ({
      ...s,
      filters: {
        ...s.filters,
        status: status === "closed" ? "closed" : "active",
      },
    }));
    loadList();
  }

  function startStatsPolling() {
    if (pollTimer || typeof window === "undefined") return;
    loadStats();
    pollTimer = window.setInterval(() => {
      if (document.visibilityState === "visible") loadStats();
    }, 30000);
  }

  function stopStatsPolling() {
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = null;
  }

  return {
    subscribe: state.subscribe,
    update: state.update,
    setActive,
    loadStats,
    loadList,
    openTicket,
    closeTicketView,
    sendReply,
    patchTicket,
    closeTicket,
    toggleInternalNote,
    setFilter,
    setStatusView,
    startStatsPolling,
    stopStatsPolling,
  };
}
