import type { components } from "../../api/openapi.generated";
import {
  unwrap,
  type ApiClient,
  buildAdminSupportStatsPath,
  buildAdminSupportPath,
  buildAdminSupportTicketMessagesPath,
  buildAdminSupportTicketPath,
  buildAdminSupportTicketReadPath,
  buildAdminSupportTicketTypingPath,
  buildAdminSupportTicketsPath,
} from "../../webapp/publicApi";
import { withRoutePrefix } from "../../webapp/routes.js";
import { createSupportTypingHeartbeat } from "../../webapp/supportTyping.js";
import { adminErrorMessage } from "../errors.js";
import { defineRawStateProperty } from "./rawStateProperty";
import { snapshotForPayload } from "./snapshotForPayload.svelte";

type AdminApi = ApiClient["api"];
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type TicketId = number | string;
type TicketViewOptions = { skipPush?: boolean };
type LoadListOptions = { silent?: boolean };
type TicketPatch = Partial<components["schemas"]["AdminTicketPatchPayload"]>;
type TicketReplyPayload = components["schemas"]["AdminTicketReplyPayload"];
type BaseSupportTicket = components["schemas"]["SupportTicketOut"];
type AdminSupportTicket = components["schemas"]["AdminSupportTicketOut"];
type AdminSupportUser = components["schemas"]["AdminSupportUserOut"];
type AdminSupportUserSnapshot = components["schemas"]["AdminSupportUserSnapshotOut"];
export type SupportStats = components["schemas"]["AdminSupportStatsOut"];

export type SupportFilters = {
  status: string;
  priority: string;
  category: string;
  search: string;
  sort: string;
};

export type SupportUser = Partial<AdminSupportUser & AdminSupportUserSnapshot> &
  Record<string, unknown>;

export type SupportTicket = BaseSupportTicket & {
  user?: AdminSupportTicket["user"] | SupportUser;
};

export type SupportMessage = components["schemas"]["AdminSupportMessageOut"];

export type AdminSupportState = {
  tickets: SupportTicket[];
  stats: SupportStats;
  filters: SupportFilters;
  loading: boolean;
  openedTicketId: number | null;
  openedTicket: SupportTicket | null;
  messages: SupportMessage[];
  peerTyping: boolean;
  userSnapshot: SupportUser | null;
  detailLoading: boolean;
  sending: boolean;
  composerInternalNote: boolean;
};

type RawSupportState = Pick<AdminSupportState, "tickets" | "messages">;
type ProxiedSupportState = Omit<AdminSupportState, keyof RawSupportState>;

type AdminSupportStoreOptions = {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
  routePrefix?: string;
};

export type AdminSupportStore = AdminSupportState & {
  setActive(section: string): void;
  loadStats(): Promise<void>;
  loadList(options?: LoadListOptions): Promise<void>;
  openTicket(ticketId: TicketId, opts?: TicketViewOptions): Promise<void>;
  closeTicketView(opts?: TicketViewOptions): void;
  sendReply(body: string): Promise<boolean | undefined>;
  notifyTyping(typing: boolean): void;
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
    awaiting_user: Number(record.awaiting_user ?? fallback.awaiting_user ?? 0),
    awaiting_admin: Number(record.awaiting_admin ?? fallback.awaiting_admin ?? 0),
    total: Number(record.total ?? fallback.total ?? 0),
    total_unread_admin: Number(record.total_unread_admin ?? fallback.total_unread_admin ?? 0),
  };
}

function mergeTicket(
  current: SupportTicket | null,
  incoming: BaseSupportTicket | SupportTicket
): SupportTicket {
  const existingUser = current?.user;
  const incomingUser = "user" in incoming ? incoming.user : undefined;
  return {
    ...(current || incoming),
    ...incoming,
    user: incomingUser || existingUser,
  } as SupportTicket;
}

function mergeTicketValue(current: SupportTicket | null, value: unknown): SupportTicket | null {
  const incoming = asTicket(value);
  return incoming ? mergeTicket(current, incoming) : current;
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

  let tickets = $state.raw<SupportTicket[]>([]);
  let messages = $state.raw<SupportMessage[]>([]);
  const state = $state<ProxiedSupportState>({
    stats: {
      active: 0,
      closed: 0,
      open: 0,
      awaiting_user: 0,
      awaiting_admin: 0,
      total: 0,
      total_unread_admin: 0,
    },
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
    userSnapshot: null,
    peerTyping: false,
    detailLoading: false,
    sending: false,
    composerInternalNote: false,
  });
  const store = Object.create(state) as AdminSupportStore;
  defineRawStateProperty(store, "tickets", {
    get: () => tickets,
    set: (value) => {
      tickets = value;
    },
  });
  defineRawStateProperty(store, "messages", {
    get: () => messages,
    set: (value) => {
      messages = value;
    },
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
    return snapshotForPayload({
      tickets,
      stats: state.stats,
      filters: state.filters,
      loading: state.loading,
      openedTicketId: state.openedTicketId,
      openedTicket: state.openedTicket,
      messages,
      userSnapshot: state.userSnapshot,
      peerTyping: state.peerTyping,
      detailLoading: state.detailLoading,
      sending: state.sending,
      composerInternalNote: state.composerInternalNote,
    });
  }

  function updateState(updater: (snapshot: AdminSupportState) => AdminSupportState): void {
    const current = getSnapshot();
    const next = updater(current);
    if (next === current) return;
    const { tickets: nextTickets, messages: nextMessages, ...nextState } = next;
    tickets = nextTickets;
    messages = nextMessages;
    Object.assign(state, nextState);
  }

  function currentOpenedTicketId() {
    return getSnapshot()?.openedTicketId || null;
  }

  function postTicketTyping(ticketId: number, typing: boolean) {
    return api(buildAdminSupportTicketTypingPath(ticketId), {
      method: "POST",
      body: JSON.stringify({ typing }),
    });
  }

  const typingHeartbeat = createSupportTypingHeartbeat({ send: postTicketTyping });

  function lastMessageId(messages: SupportMessage[]) {
    const list = Array.isArray(messages) ? messages : [];
    return Number(list.at(-1)?.message_id || 0);
  }

  function pushTicketPath(ticketId: number | null) {
    if (typeof window === "undefined" || window.location.protocol === "file:") return;
    if (active !== "support") return;
    const target = withRoutePrefix(buildAdminSupportPath(ticketId), routePrefix);
    if (window.location.pathname !== target) {
      window.history.pushState(
        null,
        "",
        `${target}${window.location.search}${window.location.hash}`
      );
    }
  }

  async function loadStats() {
    const res = await api(buildAdminSupportStatsPath());
    if (res?.ok) {
      const payload = unwrap(res);
      updateState((s) => ({ ...s, stats: asStats(payload.stats, s.stats) }));
    }
  }

  async function loadList(options: LoadListOptions = {}) {
    const silent = options.silent === true;
    if (!silent) updateState((s) => ({ ...s, loading: true }));
    let filters;
    filters = getSnapshot()?.filters;
    try {
      const params = new URLSearchParams({ limit: "50", offset: "0" });
      for (const [key, value] of Object.entries(filters || {})) {
        if (value) params.set(key, value);
      }
      const res = await api(buildAdminSupportTicketsPath(params));
      if (res?.ok) {
        const payload = unwrap(res);
        updateState((s) => ({ ...s, tickets: asTickets(payload.tickets) }));
      } else onToast(adminErrorMessage(res, at));
    } finally {
      if (!silent) updateState((s) => ({ ...s, loading: false }));
    }
  }

  async function refreshCurrentTicket(ticketId: TicketId) {
    const id = Number(ticketId);
    if (!id) return null;
    const res = await api(buildAdminSupportTicketPath(id));
    if (!res?.ok) return res;
    const payload = unwrap(res);

    let shouldRefreshList = false;
    let shouldMarkRead = false;
    updateState((s) => {
      if (s.openedTicketId !== id) return s;
      const nextMessages = asMessages(payload.messages);
      shouldRefreshList =
        lastMessageId(nextMessages) !== lastMessageId(s.messages) ||
        asTicket(payload.ticket)?.status !== s.openedTicket?.status ||
        Number(asTicket(payload.ticket)?.unread_admin_count || 0) !==
          Number(s.openedTicket?.unread_admin_count || 0);
      shouldMarkRead = Number(asTicket(payload.ticket)?.unread_admin_count || 0) > 0;
      return {
        ...s,
        openedTicket: asTicket(payload.ticket),
        messages: nextMessages,
        userSnapshot: asUser(payload.user_snapshot),
        peerTyping: Boolean(payload.peer_typing),
      };
    });

    if (currentOpenedTicketId() !== id) return res;
    if (shouldMarkRead) {
      await api(buildAdminSupportTicketReadPath(id), { method: "POST", body: "{}" });
      await loadStats();
      shouldRefreshList = true;
    }
    if (shouldRefreshList) await loadList({ silent: true });
    return res;
  }

  async function openTicket(ticketId: TicketId, opts: TicketViewOptions = {}) {
    const id = Number(ticketId);
    if (!id) return;
    if (currentOpenedTicketId() && currentOpenedTicketId() !== id) typingHeartbeat.stop();
    updateState((s) => ({
      ...s,
      openedTicketId: id,
      openedTicket: s.openedTicket?.ticket_id === id ? s.openedTicket : null,
      messages: s.openedTicket?.ticket_id === id ? s.messages : [],
      userSnapshot: s.openedTicket?.ticket_id === id ? s.userSnapshot : null,
      detailLoading: true,
    }));
    if (!opts.skipPush) pushTicketPath(id);
    try {
      const res = await api(buildAdminSupportTicketPath(id));
      if (res?.ok) {
        const payload = unwrap(res);
        updateState((s) =>
          s.openedTicketId === id
            ? {
                ...s,
                openedTicket: asTicket(payload.ticket),
                messages: asMessages(payload.messages),
                userSnapshot: asUser(payload.user_snapshot),
                peerTyping: Boolean(payload.peer_typing),
              }
            : s
        );
        if (currentOpenedTicketId() === id) {
          await api(buildAdminSupportTicketReadPath(id), { method: "POST", body: "{}" });
          await loadStats();
          await loadList({ silent: true });
          scheduleTicketPoll(OPEN_TICKET_POLL_MS);
        }
      } else onToast(adminErrorMessage(res, at, "not_found"));
    } finally {
      updateState((s) => (s.openedTicketId === id ? { ...s, detailLoading: false } : s));
    }
  }

  function closeTicketView(opts: TicketViewOptions = {}) {
    typingHeartbeat.stop();
    updateState((s) => ({
      ...s,
      openedTicketId: null,
      openedTicket: null,
      messages: [],
      userSnapshot: null,
      peerTyping: false,
    }));
    clearTicketPollTimer();
    if (!opts.skipPush) pushTicketPath(null);
  }

  async function sendReply(body: string) {
    const snapshot = getSnapshot();
    if (snapshot.sending) return false;
    const current = snapshot.openedTicketId;
    const internal = snapshot.composerInternalNote;
    updateState((s) => ({ ...s, sending: true }));
    if (!current) {
      updateState((s) => ({ ...s, sending: false }));
      return;
    }
    typingHeartbeat.stop(current);
    try {
      const payload: TicketReplyPayload = snapshotForPayload({ body, is_internal_note: internal });
      const res = await api(buildAdminSupportTicketMessagesPath(current), {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!res?.ok) throw res;
      const response = unwrap(res);
      updateState((s) =>
        s.openedTicketId === current
          ? {
              ...s,
              openedTicket: mergeTicketValue(s.openedTicket, response.ticket),
              messages: response.message ? [...s.messages, response.message] : s.messages,
            }
          : s
      );
      void Promise.allSettled([loadList({ silent: true }), loadStats()]);
      return true;
    } catch (error) {
      onToast(adminErrorMessage(error, at, at("support_send_failed", {}, "Send failed")));
      return false;
    } finally {
      updateState((s) => ({ ...s, sending: false }));
    }
  }

  function notifyTyping(typing: boolean) {
    const snapshot = getSnapshot();
    const ticketId = snapshot.openedTicketId;
    if (!typing || !ticketId || snapshot.composerInternalNote) {
      typingHeartbeat.stop(ticketId || undefined);
      return;
    }
    typingHeartbeat.pulse(ticketId);
  }

  async function patchTicket(updates: TicketPatch) {
    let current: number | null = null;
    updateState((s) => {
      current = s.openedTicketId;
      return s;
    });
    if (!current) return;
    const res = await api(buildAdminSupportTicketPath(current), {
      method: "PATCH",
      body: JSON.stringify(snapshotForPayload(updates)),
    });
    if (res?.ok) {
      const payload = unwrap(res);
      updateState((s) => ({
        ...s,
        openedTicket: payload.ticket
          ? mergeTicket(s.openedTicket, asTicket(payload.ticket) || payload.ticket)
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
    const nextInternal = !getSnapshot().composerInternalNote;
    updateState((s) => ({ ...s, composerInternalNote: nextInternal }));
    if (nextInternal) typingHeartbeat.stop(currentOpenedTicketId() || undefined);
  }

  function setFilter(key: keyof SupportFilters, value: string) {
    updateState((s) => ({ ...s, filters: { ...s.filters, [key]: value } }));
  }

  function setStatusView(status: string) {
    updateState((s) => ({
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
      if (res && !res.ok) failed = true;
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
    typingHeartbeat.stop();
  }

  return Object.assign(store, {
    setActive,
    loadStats,
    loadList,
    openTicket,
    closeTicketView,
    sendReply,
    notifyTyping,
    patchTicket,
    closeTicket,
    toggleInternalNote,
    setFilter,
    setStatusView,
    startStatsPolling,
    stopStatsPolling,
  });
}
