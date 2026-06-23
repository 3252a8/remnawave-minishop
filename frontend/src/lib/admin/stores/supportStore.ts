import { get, writable, type Writable } from "svelte/store";
import { withRoutePrefix } from "../../webapp/routes.js";
import { adminErrorMessage } from "../errors.js";

type AdminApi = (path: string, options?: RequestInit) => Promise<Record<string, unknown>>;
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type TicketId = number | string;
type TicketViewOptions = { skipPush?: boolean };
type LoadListOptions = { silent?: boolean };
type TicketPatch = Record<string, unknown>;

export type SupportStats = {
  active: number;
  closed: number;
  open: number;
  awaiting_admin: number;
  total_unread_admin: number;
};

export type SupportFilters = {
  status: string;
  priority: string;
  category: string;
  search: string;
  sort: string;
};

export type SupportUser = Record<string, unknown> & {
  email?: string;
  first_name?: string;
  last_name?: string;
  user_id?: number | string;
  username?: string;
};

export type SupportTicket = Record<string, unknown> & {
  subject?: string;
  status?: string;
  ticket_id?: number;
  unread_admin_count?: number;
  user?: SupportUser;
};

export type SupportMessage = Record<string, unknown> & {
  author_name?: string;
  author_role?: string;
  author_user_id?: number | string;
  body?: string;
  created_at?: string;
  is_internal_note?: boolean;
  message_id?: number;
};

type AdminSupportState = {
  tickets: SupportTicket[];
  stats: SupportStats;
  filters: SupportFilters;
  loading: boolean;
  openedTicketId: number | null;
  openedTicket: SupportTicket | null;
  messages: SupportMessage[];
  userSnapshot: SupportUser | null;
  detailLoading: boolean;
  sending: boolean;
  composerInternalNote: boolean;
};

type AdminSupportStoreOptions = {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
  routePrefix?: string;
};

export type AdminSupportStore = Pick<Writable<AdminSupportState>, "subscribe" | "update"> & {
  setActive(section: string): void;
  loadStats(): Promise<void>;
  loadList(options?: LoadListOptions): Promise<void>;
  openTicket(ticketId: TicketId, opts?: TicketViewOptions): Promise<void>;
  closeTicketView(opts?: TicketViewOptions): void;
  sendReply(body: string): Promise<boolean | undefined>;
  patchTicket(updates: TicketPatch): Promise<void>;
  closeTicket(): void;
  toggleInternalNote(): void;
  setFilter(key: keyof SupportFilters, value: string): void;
  setStatusView(status: string): void;
  startStatsPolling(): void;
  stopStatsPolling(): void;
};

function asTicket(value: unknown): SupportTicket | null {
  return value && typeof value === "object" ? (value as SupportTicket) : null;
}

function asTickets(value: unknown): SupportTicket[] {
  return Array.isArray(value) ? value.filter(Boolean).map((item) => item as SupportTicket) : [];
}

function asMessages(value: unknown): SupportMessage[] {
  return Array.isArray(value) ? value.filter(Boolean).map((item) => item as SupportMessage) : [];
}

function asUser(value: unknown): SupportUser | null {
  return value && typeof value === "object" ? (value as SupportUser) : null;
}

function asStats(value: unknown, fallback: SupportStats): SupportStats {
  const record = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  return {
    active: Number(record.active ?? fallback.active ?? 0),
    closed: Number(record.closed ?? fallback.closed ?? 0),
    open: Number(record.open ?? fallback.open ?? 0),
    awaiting_admin: Number(record.awaiting_admin ?? fallback.awaiting_admin ?? 0),
    total_unread_admin: Number(record.total_unread_admin ?? fallback.total_unread_admin ?? 0),
  };
}

export function createAdminSupportStore({
  api,
  onToast,
  at,
  routePrefix = "",
}: AdminSupportStoreOptions): AdminSupportStore {
  const OPEN_TICKET_POLL_MS = 3_000;
  const STATS_POLL_MS = 30_000;
  const HIDDEN_POLL_MS = 300_000;
  const ERROR_POLL_MS = 90_000;

  const state: Writable<AdminSupportState> = writable({
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

  let statsPollTimer: number | null = null;
  let ticketPollTimer: number | null = null;
  let ticketPollInFlight = false;
  let visibilityHandler: (() => void) | null = null;
  let resumeHandler: (() => void) | null = null;
  let active = "stats";

  function setActive(section: string) {
    active = section;
  }

  function getSnapshot() {
    return get(state);
  }

  function currentOpenedTicketId() {
    return getSnapshot()?.openedTicketId || null;
  }

  function lastMessageId(messages: SupportMessage[]) {
    const list = Array.isArray(messages) ? messages : [];
    return Number(list.at(-1)?.message_id || 0);
  }

  function pushTicketPath(ticketId: number | null) {
    if (typeof window === "undefined" || window.location.protocol === "file:") return;
    if (active !== "support") return;
    const target = withRoutePrefix(
      ticketId ? `/admin/support/${ticketId}` : "/admin/support",
      routePrefix
    );
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
    if (res?.ok) state.update((s) => ({ ...s, stats: asStats(res.stats, s.stats) }));
  }

  async function loadList(options: LoadListOptions = {}) {
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
      if (res?.ok) state.update((s) => ({ ...s, tickets: asTickets(res.tickets) }));
      else if (res?.error) onToast(adminErrorMessage(res, at));
    } finally {
      if (!silent) state.update((s) => ({ ...s, loading: false }));
    }
  }

  async function refreshCurrentTicket(ticketId: TicketId) {
    const id = Number(ticketId);
    if (!id) return null;
    const res = await api(`/admin/support/tickets/${id}`);
    if (!res?.ok) return res;

    let shouldRefreshList = false;
    let shouldMarkRead = false;
    state.update((s) => {
      if (s.openedTicketId !== id) return s;
      const nextMessages = asMessages(res.messages);
      shouldRefreshList =
        lastMessageId(nextMessages) !== lastMessageId(s.messages) ||
        asTicket(res.ticket)?.status !== s.openedTicket?.status ||
        Number(asTicket(res.ticket)?.unread_admin_count || 0) !==
          Number(s.openedTicket?.unread_admin_count || 0);
      shouldMarkRead = Number(asTicket(res.ticket)?.unread_admin_count || 0) > 0;
      return {
        ...s,
        openedTicket: asTicket(res.ticket),
        messages: nextMessages,
        userSnapshot: asUser(res.user_snapshot),
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

  async function openTicket(ticketId: TicketId, opts: TicketViewOptions = {}) {
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
                openedTicket: asTicket(res.ticket),
                messages: asMessages(res.messages),
                userSnapshot: asUser(res.user_snapshot),
              }
            : s
        );
        if (currentOpenedTicketId() === id) {
          await api(`/admin/support/tickets/${id}/read`, { method: "POST", body: "{}" });
          await loadStats();
          await loadList({ silent: true });
          scheduleTicketPoll(OPEN_TICKET_POLL_MS);
        }
      } else onToast(adminErrorMessage(res, at, "not_found"));
    } finally {
      state.update((s) => (s.openedTicketId === id ? { ...s, detailLoading: false } : s));
    }
  }

  function closeTicketView(opts: TicketViewOptions = {}) {
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

  async function sendReply(body: string) {
    let current: number | null = null;
    let internal = false;
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
      state.update((s) =>
        s.openedTicketId === current
          ? {
              ...s,
              openedTicket: asTicket(res.ticket)
                ? {
                    ...s.openedTicket,
                    ...asTicket(res.ticket),
                    user: asTicket(res.ticket)?.user || s.openedTicket?.user,
                  }
                : s.openedTicket,
              messages: res.message ? [...s.messages, res.message as SupportMessage] : s.messages,
            }
          : s
      );
      void Promise.allSettled([loadList({ silent: true }), loadStats()]);
      return true;
    } catch (error) {
      onToast(adminErrorMessage(error, at, at("support_send_failed", {}, "Send failed")));
      return false;
    } finally {
      state.update((s) => ({ ...s, sending: false }));
    }
  }

  async function patchTicket(updates: TicketPatch) {
    let current: number | null = null;
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
          ? {
              ...s.openedTicket,
              ...asTicket(res.ticket),
              user: asTicket(res.ticket)?.user || s.openedTicket?.user,
            }
          : s.openedTicket,
      }));
      await loadList();
      await loadStats();
    } else onToast(adminErrorMessage(res, at, "update_failed"));
  }

  function closeTicket() {
    patchTicket({ status: "closed" });
  }

  function toggleInternalNote() {
    state.update((s) => ({ ...s, composerInternalNote: !s.composerInternalNote }));
  }

  function setFilter(key: keyof SupportFilters, value: string) {
    state.update((s) => ({ ...s, filters: { ...s.filters, [key]: value } }));
  }

  function setStatusView(status: string) {
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
