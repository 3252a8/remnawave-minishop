import { writable } from "svelte/store";

export function createSupportStore({ api, t, showToast }) {
  const OPEN_TICKET_POLL_MS = 3_000;
  const ACTIVE_POLL_MS = 8_000;
  const BACKGROUND_POLL_MS = 45_000;
  const IDLE_POLL_MS = 120_000;
  const PAUSED_POLL_MS = 300_000;
  const HIDDEN_POLL_MS = 300_000;
  const ERROR_POLL_MS = 90_000;
  const IDLE_AFTER_EMPTY_POLLS = 3;
  const PAUSE_AFTER_EMPTY_POLLS = 6;

  const state = writable({
    tickets: [],
    openedTicketId: null,
    openedTicket: null,
    messages: [],
    unreadCount: 0,
    unreadLoaded: false,
    unreadLoading: false,
    counts: { active: 0, closed: 0, awaiting_admin: 0, awaiting_user: 0, open: 0, total: 0 },
    loading: false,
    detailLoading: false,
    sending: false,
    creating: false,
    statusFilter: "active",
    polling: false,
  });

  let pollTimer = null;
  let pollingEnabled = false;
  let pollInFlight = false;
  let supportActive = false;
  let emptyUnreadPolls = 0;
  let lastUnreadCount = 0;
  let visibilityHandler = null;
  let resumeHandler = null;
  let listRequestSeq = 0;
  let listPromise = null;
  let listPromiseKey = "";
  let unreadPromise = null;

  function updateUnreadBackoff(value, countEmptyPoll = false) {
    const next = Math.max(0, Number(value || 0));
    if (countEmptyPoll && next === 0 && next === lastUnreadCount) emptyUnreadPolls += 1;
    else if (next > 0 || next !== lastUnreadCount) emptyUnreadPolls = 0;
    lastUnreadCount = next;
    return next;
  }

  function nextPollDelay() {
    if (supportActive) return ACTIVE_POLL_MS;
    if (lastUnreadCount > 0) return BACKGROUND_POLL_MS;
    if (emptyUnreadPolls >= PAUSE_AFTER_EMPTY_POLLS) return PAUSED_POLL_MS;
    if (emptyUnreadPolls >= IDLE_AFTER_EMPTY_POLLS) return IDLE_POLL_MS;
    return BACKGROUND_POLL_MS;
  }

  function getSnapshot() {
    let snapshot;
    const unsubscribe = state.subscribe((s) => {
      snapshot = s;
    });
    unsubscribe();
    return snapshot;
  }

  function activePollDelay() {
    return currentOpenedTicketId() ? OPEN_TICKET_POLL_MS : ACTIVE_POLL_MS;
  }

  function clearPollTimer() {
    if (!pollTimer) return;
    if (typeof window !== "undefined") window.clearTimeout(pollTimer);
    pollTimer = null;
  }

  function schedulePoll(delayMs = nextPollDelay()) {
    if (!pollingEnabled || typeof window === "undefined") return;
    clearPollTimer();
    pollTimer = window.setTimeout(runPollTick, Math.max(0, Number(delayMs) || 0));
  }

  function currentOpenedTicketId() {
    return getSnapshot()?.openedTicketId || null;
  }

  function hydrateUnread(value) {
    const next = updateUnreadBackoff(value);
    state.update((s) => ({
      ...s,
      unreadCount: next,
      unreadLoaded: true,
      unreadLoading: false,
    }));
  }

  async function loadList(options = {}) {
    let filter = "all";
    let hasTickets = false;
    state.update((s) => {
      filter = s.statusFilter;
      hasTickets = Boolean(s.tickets?.length);
      return s;
    });
    const requestKey = filter || "all";
    if (!options.force && listPromise && listPromiseKey === requestKey) return listPromise;

    const requestId = ++listRequestSeq;
    const showLoading = !options.silent && (options.showLoading || !hasTickets);
    if (showLoading) state.update((s) => ({ ...s, loading: true }));

    let promise;
    promise = (async () => {
      try {
        const params = new URLSearchParams({ limit: "50", offset: "0" });
        if (filter && filter !== "all") params.set("status", filter);
        const res = await api(`/support/tickets?${params.toString()}`);
        if (requestId !== listRequestSeq) return res;
        if (res?.ok)
          state.update((s) => ({
            ...s,
            tickets: res.tickets || [],
            counts: res.counts || s.counts,
          }));
        else if (res?.error) showToast(res.message || res.error);
        return res;
      } finally {
        if (requestId === listRequestSeq) {
          state.update((s) => (s.loading ? { ...s, loading: false } : s));
        }
        if (listPromise === promise) {
          listPromise = null;
          listPromiseKey = "";
        }
      }
    })();

    listPromise = promise;
    listPromiseKey = requestKey;
    return promise;
  }

  async function refreshCurrentTicket(ticketId) {
    const id = Number(ticketId);
    if (!id) return;
    try {
      const res = await api(`/support/tickets/${id}`);
      if (res?.ok) {
        state.update((s) =>
          s.openedTicketId === id
            ? {
                ...s,
                openedTicket: res.ticket,
                messages: res.messages || [],
              }
            : s
        );
        if (currentOpenedTicketId() === id && Number(res.ticket?.unread_user_count || 0) > 0) {
          await markRead(id, { silent: true });
        }
      }
      return res;
    } catch {
      return null;
    }
  }

  async function createTicket(payload) {
    state.update((s) => ({ ...s, creating: true }));
    try {
      const res = await api("/support/tickets", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!res?.ok) throw res;
      state.update((s) => ({ ...s, statusFilter: "active" }));
      await loadList({ silent: true, force: true });
      await openTicket(res.ticket.ticket_id);
      return res.ticket;
    } catch (error) {
      showToast(error?.message || t("wa_support_create_failed"));
      return null;
    } finally {
      state.update((s) => ({ ...s, creating: false }));
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
      detailLoading: true,
    }));
    if (!opts.skipPush && typeof window !== "undefined" && window.location.protocol !== "file:") {
      const target = `/support/${id}`;
      if (window.location.pathname !== target) {
        window.history.pushState(
          null,
          "",
          `${target}${window.location.search}${window.location.hash}`
        );
      }
    }
    try {
      const res = await api(`/support/tickets/${id}`);
      if (res?.ok) {
        state.update((s) =>
          s.openedTicketId === id
            ? {
                ...s,
                openedTicket: res.ticket,
                messages: res.messages || [],
              }
            : s
        );
        if (currentOpenedTicketId() === id) await markRead(id);
      } else {
        showToast(res?.message || res?.error || "not_found");
      }
    } finally {
      state.update((s) => (s.openedTicketId === id ? { ...s, detailLoading: false } : s));
      if (pollingEnabled) schedulePoll(activePollDelay());
    }
  }

  function closeTicketView(opts = {}) {
    state.update((s) => ({ ...s, openedTicketId: null, openedTicket: null, messages: [] }));
    if (!opts.skipPush && typeof window !== "undefined" && window.location.protocol !== "file:") {
      if (window.location.pathname.startsWith("/support/")) {
        window.history.pushState(
          null,
          "",
          `/support${window.location.search}${window.location.hash}`
        );
      }
    }
  }

  async function sendReply(body) {
    let ticketId = null;
    state.update((s) => {
      ticketId = s.openedTicketId;
      return { ...s, sending: true };
    });
    if (!ticketId) {
      state.update((s) => ({ ...s, sending: false }));
      return;
    }
    try {
      const res = await api(`/support/tickets/${ticketId}/messages`, {
        method: "POST",
        body: JSON.stringify({ body }),
      });
      if (!res?.ok) throw res;
      state.update((s) => ({
        ...s,
        openedTicket: res.ticket || s.openedTicket,
        messages: [...s.messages, res.message],
      }));
      await refreshUnread();
      await loadList({ silent: true, force: true });
    } catch (error) {
      showToast(error?.message || t("wa_support_send_failed"));
    } finally {
      state.update((s) => ({ ...s, sending: false }));
    }
  }

  async function markRead(ticketId = null, options = {}) {
    const id =
      ticketId ||
      (() => {
        return currentOpenedTicketId();
      })();
    if (!id) return;
    await api(`/support/tickets/${id}/read`, { method: "POST", body: "{}" });
    await refreshUnread({ silent: options.silent === true });
  }

  async function refreshUnread(options = {}) {
    if (unreadPromise) return unreadPromise;
    const silent = options.silent === true;
    if (!silent) state.update((s) => ({ ...s, unreadLoading: true }));
    unreadPromise = (async () => {
      try {
        const res = await api("/support/unread");
        if (res?.ok) {
          const unreadCount = updateUnreadBackoff(res.unread, options.countEmpty === true);
          state.update((s) => ({
            ...s,
            unreadCount,
            unreadLoaded: true,
          }));
        }
        return res;
      } finally {
        if (!silent) state.update((s) => ({ ...s, unreadLoading: false }));
        unreadPromise = null;
      }
    })();
    return unreadPromise;
  }

  function setStatusFilter(status) {
    state.update((s) => ({ ...s, statusFilter: status || "all" }));
    loadList({ force: true, showLoading: true });
  }

  async function runPollTick() {
    pollTimer = null;
    if (!pollingEnabled || typeof document === "undefined") return;
    if (document.visibilityState !== "visible") {
      schedulePoll(HIDDEN_POLL_MS);
      return;
    }
    if (pollInFlight) {
      schedulePoll(ACTIVE_POLL_MS);
      return;
    }

    pollInFlight = true;
    let failed = false;
    try {
      await refreshUnread({ silent: true, countEmpty: true });
      if (supportActive) {
        const opened = currentOpenedTicketId();
        if (opened) await refreshCurrentTicket(opened);
        else await loadList({ silent: true });
      }
    } catch (_error) {
      failed = true;
    } finally {
      pollInFlight = false;
      if (pollingEnabled) {
        schedulePoll(failed ? ERROR_POLL_MS : supportActive ? activePollDelay() : nextPollDelay());
      }
    }
  }

  function setActive(active) {
    const next = Boolean(active);
    if (supportActive === next) return;
    supportActive = next;
    if (supportActive) emptyUnreadPolls = 0;
    if (pollingEnabled) schedulePoll(supportActive ? 0 : nextPollDelay());
  }

  function startPolling(options = {}) {
    const includeList = options.includeList !== false;
    if (typeof window === "undefined") return;
    pollingEnabled = true;
    if (includeList) supportActive = true;
    state.update((s) => (s.polling ? s : { ...s, polling: true }));
    if (!visibilityHandler && typeof document !== "undefined") {
      visibilityHandler = () => {
        if (!pollingEnabled) return;
        if (document.visibilityState === "visible") {
          emptyUnreadPolls = 0;
          schedulePoll(0);
        } else {
          schedulePoll(HIDDEN_POLL_MS);
        }
      };
      document.addEventListener("visibilitychange", visibilityHandler);
    }
    if (!resumeHandler) {
      resumeHandler = () => {
        if (!pollingEnabled) return;
        if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
        emptyUnreadPolls = 0;
        schedulePoll(0);
      };
      window.addEventListener("focus", resumeHandler);
      window.addEventListener("pageshow", resumeHandler);
    }
    if (!pollTimer && !pollInFlight) {
      schedulePoll(supportActive ? 0 : nextPollDelay());
    } else if (supportActive) {
      schedulePoll(activePollDelay());
    }
  }

  function stopVisibilityListener() {
    if (!visibilityHandler || typeof document === "undefined") return;
    document.removeEventListener("visibilitychange", visibilityHandler);
    visibilityHandler = null;
  }

  function stopResumeListeners() {
    if (!resumeHandler || typeof window === "undefined") return;
    window.removeEventListener("focus", resumeHandler);
    window.removeEventListener("pageshow", resumeHandler);
    resumeHandler = null;
  }

  function closePolling() {
    pollingEnabled = false;
    supportActive = false;
    pollInFlight = false;
    emptyUnreadPolls = 0;
    clearPollTimer();
    stopVisibilityListener();
    stopResumeListeners();
    state.update((s) => (s.polling ? { ...s, polling: false } : s));
  }

  return {
    subscribe: state.subscribe,
    update: state.update,
    loadList,
    hydrateUnread,
    createTicket,
    openTicket,
    closeTicketView,
    sendReply,
    markRead,
    refreshUnread,
    setStatusFilter,
    setActive,
    startPolling,
    closePolling,
  };
}
