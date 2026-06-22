import { get, writable } from "svelte/store";
import { withRoutePrefix } from "../routes.js";
import type {
  ApiClient,
  PostPayload,
  SupportTicketDetailResponse,
  SupportTicketReadResponse,
  SupportTicketReplyResponse,
  SupportTicketsResponse,
} from "../publicApi";
import { unwrap } from "../publicApi";

type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type TicketRecord = Record<string, unknown> & { ticket_id?: number; unread_user_count?: number };
type MessageRecord = Record<string, unknown>;
type CountsRecord = {
  active: number;
  closed: number;
  awaiting_admin: number;
  awaiting_user: number;
  open: number;
  total: number;
};
type SupportState = {
  tickets: TicketRecord[];
  openedTicketId: number | null;
  openedTicket: TicketRecord | null;
  messages: MessageRecord[];
  unreadCount: number;
  unreadLoaded: boolean;
  unreadLoading: boolean;
  counts: CountsRecord;
  loading: boolean;
  detailLoading: boolean;
  sending: boolean;
  creating: boolean;
  statusFilter: string;
  polling: boolean;
};
type LoadListOptions = {
  force?: boolean;
  silent?: boolean;
  showLoading?: boolean;
};
type TicketViewOptions = {
  skipPush?: boolean;
};
type RefreshUnreadOptions = {
  silent?: boolean;
  countEmpty?: boolean;
};
type StartPollingOptions = {
  includeList?: boolean;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function arrayRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item) => item && typeof item === "object") : [];
}

function countsRecord(value: unknown, fallback: CountsRecord): CountsRecord {
  const record = asRecord(value);
  return {
    active: Number(record.active ?? fallback.active ?? 0),
    closed: Number(record.closed ?? fallback.closed ?? 0),
    awaiting_admin: Number(record.awaiting_admin ?? fallback.awaiting_admin ?? 0),
    awaiting_user: Number(record.awaiting_user ?? fallback.awaiting_user ?? 0),
    open: Number(record.open ?? fallback.open ?? 0),
    total: Number(record.total ?? fallback.total ?? 0),
  };
}

function stringField(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function createSupportStore({
  api,
  t,
  showToast,
  routePrefix = "",
}: {
  api: ApiClient["api"];
  t: Translate;
  showToast: (message: string) => void;
  routePrefix?: string;
}) {
  const OPEN_TICKET_POLL_MS = 3_000;
  const ACTIVE_POLL_MS = 8_000;
  const BACKGROUND_POLL_MS = 45_000;
  const IDLE_POLL_MS = 120_000;
  const PAUSED_POLL_MS = 300_000;
  const HIDDEN_POLL_MS = 300_000;
  const ERROR_POLL_MS = 90_000;
  const IDLE_AFTER_EMPTY_POLLS = 3;
  const PAUSE_AFTER_EMPTY_POLLS = 6;

  const state = writable<SupportState>({
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

  let pollTimer: number | null = null;
  let pollingEnabled = false;
  let pollInFlight = false;
  let supportActive = false;
  let emptyUnreadPolls = 0;
  let lastUnreadCount = 0;
  let visibilityHandler: (() => void) | null = null;
  let resumeHandler: (() => void) | null = null;
  let listRequestSeq = 0;
  let listPromise: Promise<SupportTicketsResponse> | null = null;
  let listPromiseKey = "";
  let unreadPromise: Promise<unknown> | null = null;

  function fetchTicketList(path: string): Promise<SupportTicketsResponse> {
    return api(path as "/support/tickets");
  }

  function fetchTicketDetail(id: number): Promise<SupportTicketDetailResponse> {
    return api(`/support/tickets/${id}` as "/support/tickets/{id}");
  }

  function postTicketReply(
    id: number,
    payload: PostPayload<"/api/support/tickets/{id}/messages">
  ): Promise<SupportTicketReplyResponse> {
    return api(`/support/tickets/${id}/messages` as "/support/tickets/{id}/messages", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  function postTicketRead(id: number): Promise<SupportTicketReadResponse> {
    return api(`/support/tickets/${id}/read` as "/support/tickets/{id}/read", {
      method: "POST",
      body: "{}",
    });
  }

  function updateUnreadBackoff(value: unknown, countEmptyPoll = false) {
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

  function getSnapshot(): SupportState {
    return get(state);
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

  function hydrateUnread(value: unknown) {
    const next = updateUnreadBackoff(value);
    state.update((s) => ({
      ...s,
      unreadCount: next,
      unreadLoaded: true,
      unreadLoading: false,
    }));
  }

  async function loadList(options: LoadListOptions = {}) {
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

    let promise: Promise<SupportTicketsResponse>;
    promise = (async () => {
      try {
        const params = new URLSearchParams({ limit: "50", offset: "0" });
        if (filter && filter !== "all") params.set("status", filter);
        const res = await fetchTicketList(`/support/tickets?${params.toString()}`);
        if (requestId !== listRequestSeq) return res;
        if (res?.ok) {
          const payload = unwrap(res);
          state.update((s) => ({
            ...s,
            tickets: arrayRecords(payload.tickets) as TicketRecord[],
            counts: countsRecord(payload.counts, s.counts),
          }));
        } else if (asRecord(res).error) {
          showToast(stringField(asRecord(res).message) || stringField(asRecord(res).error));
        }
        return res;
      } finally {
        if (requestId === listRequestSeq) {
          state.update((s) => (s.loading ? { ...s, loading: false } : s));
        }
        if (requestId === listRequestSeq && listPromiseKey === requestKey) {
          listPromise = null;
          listPromiseKey = "";
        }
      }
    })();

    listPromise = promise;
    listPromiseKey = requestKey;
    return promise;
  }

  async function refreshCurrentTicket(ticketId: number | string | null) {
    const id = Number(ticketId);
    if (!id) return;
    try {
      const res = await fetchTicketDetail(id);
      if (res?.ok) {
        const payload = unwrap(res);
        const ticket = asRecord(payload.ticket) as TicketRecord;
        state.update((s) =>
          s.openedTicketId === id
            ? {
                ...s,
                openedTicket: ticket,
                messages: arrayRecords(payload.messages) as MessageRecord[],
              }
            : s
        );
        if (currentOpenedTicketId() === id && Number(ticket.unread_user_count || 0) > 0) {
          await markRead(id, { silent: true });
        }
      }
      return res;
    } catch {
      return null;
    }
  }

  async function createTicket(payload: PostPayload<"/api/support/tickets">) {
    state.update((s) => ({ ...s, creating: true }));
    try {
      const res = await api("/support/tickets", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!res?.ok) throw res;
      const responsePayload = unwrap(res);
      const ticket = asRecord(responsePayload.ticket) as TicketRecord;
      state.update((s) => ({ ...s, statusFilter: "active" }));
      await loadList({ silent: true, force: true });
      await openTicket(ticket.ticket_id || 0);
      return ticket;
    } catch (error: unknown) {
      showToast(stringField(asRecord(error).message) || t("wa_support_create_failed"));
      return null;
    } finally {
      state.update((s) => ({ ...s, creating: false }));
    }
  }

  async function openTicket(ticketId: number | string, opts: TicketViewOptions = {}) {
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
      const target = withRoutePrefix(`/support/${id}`, routePrefix);
      if (window.location.pathname !== target) {
        window.history.pushState(
          null,
          "",
          `${target}${window.location.search}${window.location.hash}`
        );
      }
    }
    try {
      const res = await fetchTicketDetail(id);
      if (res?.ok) {
        const payload = unwrap(res);
        const ticket = asRecord(payload.ticket) as TicketRecord;
        state.update((s) =>
          s.openedTicketId === id
            ? {
                ...s,
                openedTicket: ticket,
                messages: arrayRecords(payload.messages) as MessageRecord[],
              }
            : s
        );
        if (currentOpenedTicketId() === id) await markRead(id);
      } else {
        showToast(
          stringField(asRecord(res).message) || stringField(asRecord(res).error) || "not_found"
        );
      }
    } finally {
      state.update((s) => (s.openedTicketId === id ? { ...s, detailLoading: false } : s));
      if (pollingEnabled) schedulePoll(activePollDelay());
    }
  }

  function closeTicketView(opts: TicketViewOptions = {}) {
    state.update((s) => ({ ...s, openedTicketId: null, openedTicket: null, messages: [] }));
    if (!opts.skipPush && typeof window !== "undefined" && window.location.protocol !== "file:") {
      const supportPath = withRoutePrefix("/support", routePrefix);
      if (window.location.pathname.startsWith(`${supportPath}/`)) {
        window.history.pushState(
          null,
          "",
          `${supportPath}${window.location.search}${window.location.hash}`
        );
      }
    }
  }

  async function sendReply(body: string) {
    let ticketId: number | null = null;
    state.update((s) => {
      ticketId = s.openedTicketId;
      return { ...s, sending: true };
    });
    if (!ticketId) {
      state.update((s) => ({ ...s, sending: false }));
      return false;
    }
    try {
      const res = await postTicketReply(ticketId, { body });
      if (!res?.ok) throw res;
      const payload = unwrap(res);
      state.update((s) =>
        s.openedTicketId === ticketId
          ? {
              ...s,
              openedTicket: payload.ticket
                ? (asRecord(payload.ticket) as TicketRecord)
                : s.openedTicket,
              messages: payload.message
                ? [...s.messages, asRecord(payload.message) as MessageRecord]
                : s.messages,
            }
          : s
      );
      void Promise.allSettled([
        refreshUnread({ silent: true }),
        loadList({ silent: true, force: true }),
      ]);
      return true;
    } catch (error: unknown) {
      showToast(stringField(asRecord(error).message) || t("wa_support_send_failed"));
      return false;
    } finally {
      state.update((s) => ({ ...s, sending: false }));
    }
  }

  async function markRead(ticketId: number | null = null, options: RefreshUnreadOptions = {}) {
    const id =
      ticketId ||
      (() => {
        return currentOpenedTicketId();
      })();
    if (!id) return;
    const response = await postTicketRead(id);
    if (response?.ok) unwrap(response);
    await refreshUnread({ silent: options.silent === true });
  }

  async function refreshUnread(options: RefreshUnreadOptions = {}) {
    if (unreadPromise) return unreadPromise;
    const silent = options.silent === true;
    if (!silent) state.update((s) => ({ ...s, unreadLoading: true }));
    unreadPromise = (async () => {
      try {
        const res = await api("/support/unread");
        if (res?.ok) {
          const payload = unwrap(res);
          const unreadCount = updateUnreadBackoff(payload.unread, options.countEmpty === true);
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

  function setStatusFilter(status: string) {
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

  function setActive(active: boolean) {
    const next = Boolean(active);
    if (supportActive === next) return;
    supportActive = next;
    if (supportActive) emptyUnreadPolls = 0;
    if (pollingEnabled) schedulePoll(supportActive ? 0 : nextPollDelay());
  }

  function startPolling(options: StartPollingOptions = {}) {
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
