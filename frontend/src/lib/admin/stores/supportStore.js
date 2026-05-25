import { writable } from "svelte/store";

export function createAdminSupportStore({ api, onToast, at }) {
  const OPEN_TICKET_POLL_MS = 3_000;
  const STATS_POLL_MS = 30_000;
  const HIDDEN_POLL_MS = 300_000;
  const ERROR_POLL_MS = 90_000;

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

  let statsPollTimer = null;
  let ticketPollTimer = null;
  let ticketPollInFlight = false;
  let visibilityHandler = null;
  let resumeHandler = null;
  let active = "stats";

  function setActive(section) {
    active = section;
  }

  function getSnapshot() {
    let snapshot;
    const unsubscribe = state.subscribe((s) => {
      snapshot = s;
    });
    unsubscribe();
    return snapshot;
  }

  function currentOpenedTicketId() {
    return getSnapshot()?.openedTicketId || null;
  }

  function lastMessageId(messages) {
    const list = Array.isArray(messages) ? messages : [];
    return Number(list.at(-1)?.message_id || 0);
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

  async function loadList(options = {}) {
    const silent = options.silent === true;
    if (!silent) state.update((s) => ({ ...s, loading: true }));
    let filters;
    filters = getSnapshot()?.filters;
    try {
      const params = new URLSearchParams({ limit: "50", offset: "0" });
      for (const [key, value] of Object.entries(filters || {})) {
        if (value) params.set(key, value);
      }
      const res = await api(`/admin/support/tickets?${params.toString()}`);
      if (res?.ok) state.update((s) => ({ ...s, tickets: res.tickets || [] }));
      else if (res?.error) onToast(res.message || res.error);
    } finally {
      if (!silent) state.update((s) => ({ ...s, loading: false }));
    }
  }

  async function refreshCurrentTicket(ticketId) {
    const id = Number(ticketId);
    if (!id) return null;
    const res = await api(`/admin/support/tickets/${id}`);
    if (!res?.ok) return res;

    let shouldRefreshList = false;
    let shouldMarkRead = false;
    state.update((s) => {
      if (s.openedTicketId !== id) return s;
      const nextMessages = res.messages || [];
      shouldRefreshList =
        lastMessageId(nextMessages) !== lastMessageId(s.messages) ||
        res.ticket?.status !== s.openedTicket?.status ||
        Number(res.ticket?.unread_admin_count || 0) !==
          Number(s.openedTicket?.unread_admin_count || 0);
      shouldMarkRead = Number(res.ticket?.unread_admin_count || 0) > 0;
      return {
        ...s,
        openedTicket: res.ticket,
        messages: nextMessages,
        userSnapshot: res.user_snapshot || null,
      };
    });

    if (currentOpenedTicketId() !== id) return res;
    if (shouldMarkRead) {
      await api(`/admin/support/tickets/${id}/read`, { method: "POST", body: "{}" });
      await loadStats();
      shouldRefreshList = true;
    }
    if (shouldRefreshList) await loadList({ silent: true });
    return res;
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
        state.update((s) =>
          s.openedTicketId === id
            ? {
                ...s,
                openedTicket: res.ticket,
                messages: res.messages || [],
                userSnapshot: res.user_snapshot || null,
              }
            : s
        );
        if (currentOpenedTicketId() === id) {
          await api(`/admin/support/tickets/${id}/read`, { method: "POST", body: "{}" });
          await loadStats();
          await loadList({ silent: true });
          scheduleTicketPoll(OPEN_TICKET_POLL_MS);
        }
      } else onToast(res?.message || res?.error || "not_found");
    } finally {
      state.update((s) => (s.openedTicketId === id ? { ...s, detailLoading: false } : s));
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
    clearTicketPollTimer();
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
    if (!current) {
      state.update((s) => ({ ...s, sending: false }));
      return;
    }
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

  function clearTicketPollTimer() {
    if (!ticketPollTimer || typeof window === "undefined") return;
    window.clearTimeout(ticketPollTimer);
    ticketPollTimer = null;
  }

  function scheduleTicketPoll(delayMs = OPEN_TICKET_POLL_MS) {
    if (typeof window === "undefined") return;
    clearTicketPollTimer();
    if (!currentOpenedTicketId()) return;
    ticketPollTimer = window.setTimeout(runTicketPoll, Math.max(0, Number(delayMs) || 0));
  }

  async function runTicketPoll() {
    ticketPollTimer = null;
    if (typeof document !== "undefined" && document.visibilityState !== "visible") {
      scheduleTicketPoll(HIDDEN_POLL_MS);
      return;
    }
    const ticketId = currentOpenedTicketId();
    if (!ticketId) return;
    if (ticketPollInFlight) {
      scheduleTicketPoll(OPEN_TICKET_POLL_MS);
      return;
    }

    ticketPollInFlight = true;
    let failed = false;
    try {
      const res = await refreshCurrentTicket(ticketId);
      if (res?.error) failed = true;
    } catch (_error) {
      failed = true;
    } finally {
      ticketPollInFlight = false;
      if (currentOpenedTicketId()) {
        scheduleTicketPoll(failed ? ERROR_POLL_MS : OPEN_TICKET_POLL_MS);
      }
    }
  }

  function ensureRealtimeListeners() {
    if (typeof window === "undefined") return;
    if (!visibilityHandler && typeof document !== "undefined") {
      visibilityHandler = () => {
        if (document.visibilityState === "visible") {
          loadStats();
          scheduleTicketPoll(0);
        } else {
          scheduleTicketPoll(HIDDEN_POLL_MS);
        }
      };
      document.addEventListener("visibilitychange", visibilityHandler);
    }
    if (!resumeHandler) {
      resumeHandler = () => {
        if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
        loadStats();
        scheduleTicketPoll(0);
      };
      window.addEventListener("focus", resumeHandler);
      window.addEventListener("pageshow", resumeHandler);
    }
  }

  function stopRealtimeListeners() {
    if (visibilityHandler && typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", visibilityHandler);
      visibilityHandler = null;
    }
    if (resumeHandler && typeof window !== "undefined") {
      window.removeEventListener("focus", resumeHandler);
      window.removeEventListener("pageshow", resumeHandler);
      resumeHandler = null;
    }
  }

  function startStatsPolling() {
    if (typeof window === "undefined") return;
    ensureRealtimeListeners();
    if (statsPollTimer) return;
    loadStats();
    statsPollTimer = window.setInterval(() => {
      if (document.visibilityState === "visible") loadStats();
    }, STATS_POLL_MS);
  }

  function stopStatsPolling() {
    if (statsPollTimer) window.clearInterval(statsPollTimer);
    statsPollTimer = null;
    clearTicketPollTimer();
    ticketPollInFlight = false;
    stopRealtimeListeners();
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
