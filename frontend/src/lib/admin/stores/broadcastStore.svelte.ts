import { adminErrorMessage } from "../errors.js";
import type { MessageShortcodeInfo } from "$lib/richtext/editorSchema";
import {
  buildAdminBroadcastAudienceCountsPath,
  buildAdminBroadcastItemPath,
  buildAdminBroadcastPath,
  buildAdminBroadcastPreviewPath,
  buildAdminBroadcastShortcodesPath,
  buildAdminBroadcastsPath,
  buildAdminPromoOptionsPath,
  unwrap,
  type ApiClient,
  type GetResponse,
  type PatchPayload,
  type PostPayload,
} from "../../webapp/publicApi";
import type { components } from "../../api/openapi.generated";
import { historyItemFromWire, type BroadcastHistoryItem } from "./broadcastHistory";
import { snapshotForPayload } from "./snapshotForPayload.svelte";
import { messageRequestBody } from "$lib/messageImage";
import { normalizeMessageButtonLink } from "$lib/admin/messageButtonTargets.js";

type AdminApi = ApiClient["api"];
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type BroadcastCounts = Record<string, number>;
type BroadcastResult = { queued: number; failed: number; emailQueued: number; channels: string[] };
export type BroadcastTargetOption = {
  value: string;
  label: string;
  disabled?: boolean;
  locked?: boolean;
  group?: string;
  icon?: string;
};
type BroadcastAudienceDescriptor = {
  target: string;
  labelKey: string;
  fallbackLabel: string;
  order: number;
  available: boolean;
  groupLabelKey: string | null;
  groupFallbackLabel: string | null;
  icon: string | null;
};
type StoredCounts = {
  counts: BroadcastCounts;
  loadedAt: number;
  emailAvailable: boolean | null;
  audiences: BroadcastAudienceDescriptor[] | null;
};
export type BroadcastButtonKind = "url" | "promo_bot" | "promo_webapp" | "webapp_section";
export type BroadcastButtonDraft = {
  id: number;
  kind: BroadcastButtonKind;
  label: string;
  url: string;
  promoCode: string;
  /** Web app screen a ``webapp_section`` button opens. */
  section: string;
  /**
   * Author's own caption per language code. Empty everywhere is the normal
   * case: the button then shows the prepared caption for its kind in the
   * recipient's own language.
   */
  labels?: Record<string, string>;
};
export type BroadcastPromoOption = { value: string; label: string; group?: string };
/** A message addressed to one customer, composed outside the broadcast draft. */
export type SingleUserMessage = {
  userId: number;
  text: string;
  channels: string[];
  emailSubject: string;
  buttons: BroadcastButtonDraft[];
  image?: File | null;
};
/** Kept as the broadcast-flavoured name of the shared composer type. */
export type BroadcastShortcodeInfo = MessageShortcodeInfo;
export type BroadcastPreviewResult = {
  renderedText: string;
  renderedSubject: string | null;
  unknownShortcodes: string[];
  length: number;
  sent: boolean;
};
export type BroadcastState = {
  broadcastTarget: string;
  broadcastTargetError: string | null;
  broadcastText: string;
  broadcastTexts: Record<string, string>;
  broadcastImage: File | null;
  broadcastLanguage: string;
  broadcastBusy: boolean;
  broadcastResult: BroadcastResult | null;
  broadcastCounts: BroadcastCounts | null;
  broadcastCountsLoading: boolean;
  broadcastCountsLoadedAt: number;
  broadcastAudiencesLoaded: boolean;
  broadcastTelegramEnabled: boolean;
  broadcastEmailEnabled: boolean;
  broadcastEmailAvailable: boolean;
  broadcastEmailAvailabilityKnown: boolean;
  broadcastEmailSubject: string;
  broadcastEmailSubjects: Record<string, string>;
  broadcastButtons: BroadcastButtonDraft[];
  broadcastPromoOptions: BroadcastPromoOption[];
  broadcastPromoOptionsLoading: boolean;
  broadcastPromoOptionsLoaded: boolean;
  broadcastShortcodes: BroadcastShortcodeInfo[];
  broadcastAllowedTags: string[];
  broadcastShortcodesLoading: boolean;
  broadcastShortcodesLoaded: boolean;
  broadcastPreviewBusy: boolean;
  broadcastPreviewResult: BroadcastPreviewResult | null;
  broadcastScheduleEnabled: boolean;
  broadcastScheduledAt: string;
  broadcastHistory: BroadcastHistoryItem[];
  broadcastHistoryLoading: boolean;
  broadcastHistoryLoaded: boolean;
};
type BroadcastStoreOptions = {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
};
export type BroadcastStore = BroadcastState & {
  runBroadcast: () => Promise<void>;
  updateField: (fields: Partial<BroadcastState>) => void;
  loadCounts: (options?: { force?: boolean }) => Promise<void>;
  addButton: () => void;
  removeButton: (index: number) => void;
  updateButton: (index: number, fields: Partial<BroadcastButtonDraft>) => void;
  moveButton: (from: number, to: number) => void;
  loadPromoOptions: (query?: string) => Promise<void>;
  loadShortcodes: () => Promise<void>;
  sendPreview: (mode: "render" | "send_telegram", userId?: number | null) => Promise<void>;
  sendToUser: (input: SingleUserMessage) => Promise<string | null>;
  loadHistory: () => Promise<void>;
  deleteBroadcast: (broadcastId: number) => Promise<void>;
  rescheduleBroadcast: (broadcastId: number, localDateTime: string) => Promise<boolean>;
  canSubmit: () => boolean;
  BROADCAST_TARGET_OPTIONS: BroadcastTargetOption[];
  MAX_BROADCAST_BUTTONS: number;
};

export const MAX_BROADCAST_BUTTONS = 4;

function buttonDraftValid(button: BroadcastButtonDraft): boolean {
  // An empty caption is no longer a mistake: the button then shows the
  // prepared caption for its kind in the recipient's own language.
  if (button.label.trim().length > 64) return false;
  if (Object.values(button.labels ?? {}).some((label) => label.trim().length > 64)) return false;
  if (button.kind === "url") {
    return normalizeMessageButtonLink(button.url) !== null;
  }
  if (button.kind === "webapp_section") return Boolean(button.section.trim());
  return /^[A-Za-z0-9_-]{1,58}$/.test(button.promoCode.trim());
}

function localizedForPayload(values: Record<string, string> | undefined): Record<string, string> {
  const payload: Record<string, string> = {};
  for (const [language, text] of Object.entries(values ?? {})) {
    const body = String(text ?? "").trim();
    // An empty tab means "not written yet"; sending it would deliver an empty
    // caption to exactly the customers who read that language.
    if (body) payload[language.toLowerCase()] = body;
  }
  return payload;
}

/** Drafted buttons as the message contract expects them, shared with support. */
export function buttonsForPayload(buttons: BroadcastButtonDraft[]) {
  return buttons.map((button) => ({
    kind: button.kind,
    label: button.label.trim(),
    labels: localizedForPayload(button.labels),
    url: button.kind === "url" ? normalizeMessageButtonLink(button.url) || button.url.trim() : "",
    promo_code:
      button.kind === "url" || button.kind === "webapp_section" ? "" : button.promoCode.trim(),
    section: button.kind === "webapp_section" ? button.section.trim() : "",
  }));
}

type PromoListItem = components["schemas"]["PromoOptionOut"];
type PromosListResponse = GetResponse<"/api/admin/promos/options">;

/**
 * A code minted for one named customer.
 *
 * Ownership is explicit: only ``user_id`` marks a code as personal. A code
 * that merely allows a single activation is still an ordinary shared code and
 * stays in the shared group.
 */
function promoIsPersonal(promo: PromoListItem): boolean {
  return Boolean(promo.user_id);
}

function promoOptionLabel(promo: PromoListItem): string {
  const code = String(promo.code || "");
  const max = Number(promo.max_activations);
  const current = Number(promo.current_activations);
  if (Number.isFinite(max) && max > 0 && Number.isFinite(current)) {
    return `${code} · ${current}/${max}`;
  }
  return code;
}

function isPromosListResponse(value: unknown): value is PromosListResponse {
  return Boolean(value && typeof value === "object" && (value as { ok?: unknown }).ok === true);
}

function promoOptionsFromResponse(
  response: PromosListResponse,
  at: TranslateFn
): BroadcastPromoOption[] {
  const sharedGroup = at("broadcast_promo_group_shared", {}, "Shared codes");
  const personalGroup = at("broadcast_promo_group_personal", {}, "Personal codes");
  const options = (response.promos || [])
    .map((promo) => ({
      value: String(promo.code || ""),
      label: promoOptionLabel(promo),
      group: promoIsPersonal(promo) ? personalGroup : sharedGroup,
    }))
    .filter((option) => option.value);
  // Keep ownership visually strict even when the server ranks one exact
  // personal match above similar shared codes: shared is always the first group.
  return [
    ...options.filter((option) => option.group === sharedGroup),
    ...options.filter((option) => option.group === personalGroup),
  ];
}

function asBroadcastCounts(value: unknown): BroadcastCounts | null {
  if (!value || typeof value !== "object") return null;
  return Object.fromEntries(
    Object.entries(value).map(([key, count]) => {
      const numericCount = Number(count);
      return [key, Number.isFinite(numericCount) ? numericCount : 0];
    })
  );
}

function asBroadcastAudiences(value: unknown): BroadcastAudienceDescriptor[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  return value
    .map((item) => {
      const raw = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
      return {
        target: String(raw.target || "")
          .trim()
          .toLowerCase(),
        labelKey: String(raw.label_key || "").trim(),
        fallbackLabel: String(raw.fallback_label || "").trim(),
        order: Number.isFinite(Number(raw.order)) ? Number(raw.order) : 100,
        available: raw.available !== false,
        groupLabelKey: String(raw.group_label_key || "").trim() || null,
        groupFallbackLabel: String(raw.group_fallback_label || "").trim() || null,
        icon: String(raw.icon || "").trim() || null,
      };
    })
    .filter((item) => {
      if (!item.target || !item.labelKey || !item.fallbackLabel || seen.has(item.target)) {
        return false;
      }
      seen.add(item.target);
      return true;
    })
    .sort((left, right) => left.order - right.order || left.target.localeCompare(right.target));
}

export function createBroadcastStore({ api, onToast, at }: BroadcastStoreOptions): BroadcastStore {
  const COUNTS_CACHE_TTL_MS = 30_000;
  const COUNTS_DISPLAY_CACHE_TTL_MS = 5 * 60_000;
  const COUNTS_STORAGE_KEY = "remnawave-admin:broadcast-audience-counts";
  let countsPromise: Promise<void> | null = null;
  let promoOptionsPromise: Promise<void> | null = null;
  let promoOptionsRequestId = 0;
  let promoOptionsQuery = "";
  const promoOptionsCache = new Map<string, BroadcastPromoOption[]>();
  let shortcodesPromise: Promise<void> | null = null;
  let historyPromise: Promise<void> | null = null;
  let buttonIdCounter = 0;
  const subscriptionGroup = () =>
    at("broadcast_audience_group_subscription", {}, "Subscription status");
  const rolesGroup = () => at("broadcast_audience_group_roles", {}, "Roles");

  const CORE_BROADCAST_TARGET_OPTIONS: BroadcastTargetOption[] = [
    {
      value: "all",
      label: at("broadcast_target_all", {}, "All active"),
      group: subscriptionGroup(),
      icon: "users",
    },
    {
      value: "active",
      label: at("broadcast_target_active", {}, "With subscription"),
      group: subscriptionGroup(),
      icon: "shield-check",
    },
    {
      value: "inactive",
      label: at("broadcast_target_inactive", {}, "No subscription"),
      group: subscriptionGroup(),
      icon: "user",
    },
    {
      value: "expired",
      label: at("broadcast_target_expired", {}, "Expired subscription"),
      group: subscriptionGroup(),
      icon: "calendar-days",
    },
    {
      value: "active_never_connected",
      label: at(
        "broadcast_target_active_never_connected",
        {},
        "With subscription, no VPN connections"
      ),
      group: subscriptionGroup(),
      icon: "shield",
    },
    {
      value: "never",
      label: at("broadcast_target_never", {}, "No subscription, no history"),
      group: subscriptionGroup(),
      icon: "moon",
    },
    {
      value: "admins",
      label: at("broadcast_target_admins", {}, "Administrators (broadcast test)"),
      group: rolesGroup(),
      icon: "crown",
    },
  ];

  function targetOptions(audiences: BroadcastAudienceDescriptor[]): BroadcastTargetOption[] {
    const reserved = new Set(CORE_BROADCAST_TARGET_OPTIONS.map((option) => option.value));
    return [
      ...CORE_BROADCAST_TARGET_OPTIONS,
      ...audiences
        .filter((audience) => !reserved.has(audience.target))
        .map((audience) => {
          const group =
            audience.groupLabelKey && audience.groupFallbackLabel
              ? at(audience.groupLabelKey, {}, audience.groupFallbackLabel)
              : undefined;
          return {
            value: audience.target,
            label: at(audience.labelKey, {}, audience.fallbackLabel),
            ...(group ? { group } : {}),
            ...(audience.icon ? { icon: audience.icon } : {}),
            ...(!audience.available ? { disabled: true, locked: true } : {}),
          };
        }),
    ];
  }

  const cachedCounts = readStoredCounts();

  const state = $state<BroadcastStore>({
    broadcastTarget: "all",
    broadcastTargetError: null,
    broadcastText: "",
    broadcastTexts: {},
    broadcastImage: null,
    broadcastLanguage: "",
    broadcastBusy: false,
    broadcastResult: null,
    broadcastCounts: cachedCounts?.counts || null,
    broadcastCountsLoading: false,
    broadcastCountsLoadedAt: cachedCounts?.loadedAt || 0,
    broadcastAudiencesLoaded:
      cachedCounts?.audiences !== null && cachedCounts?.audiences !== undefined,
    broadcastTelegramEnabled: true,
    broadcastEmailEnabled: false,
    broadcastEmailAvailable: cachedCounts?.emailAvailable ?? false,
    broadcastEmailAvailabilityKnown: typeof cachedCounts?.emailAvailable === "boolean",
    broadcastEmailSubject: "",
    broadcastEmailSubjects: {},
    broadcastButtons: [],
    broadcastPromoOptions: [],
    broadcastPromoOptionsLoading: false,
    broadcastPromoOptionsLoaded: false,
    broadcastShortcodes: [],
    broadcastAllowedTags: [],
    broadcastShortcodesLoading: false,
    broadcastShortcodesLoaded: false,
    broadcastPreviewBusy: false,
    broadcastPreviewResult: null,
    broadcastScheduleEnabled: false,
    broadcastScheduledAt: "",
    broadcastHistory: [],
    broadcastHistoryLoading: false,
    broadcastHistoryLoaded: false,
    runBroadcast,
    updateField,
    loadCounts,
    addButton,
    removeButton,
    updateButton,
    moveButton,
    loadPromoOptions,
    loadShortcodes,
    sendPreview,
    sendToUser,
    loadHistory,
    deleteBroadcast,
    rescheduleBroadcast,
    canSubmit,
    BROADCAST_TARGET_OPTIONS: targetOptions(cachedCounts?.audiences || []),
    MAX_BROADCAST_BUTTONS,
  });

  function updateState(updater: (snapshot: BroadcastStore) => BroadcastStore): void {
    const next = updater(state);
    if (next === state) return;
    Object.assign(state, next);
  }

  function countsAreFresh(stateSnapshot: BroadcastState): boolean {
    return Boolean(
      stateSnapshot.broadcastCounts &&
      stateSnapshot.broadcastAudiencesLoaded &&
      stateSnapshot.broadcastEmailAvailabilityKnown &&
      Date.now() - Number(stateSnapshot.broadcastCountsLoadedAt || 0) < COUNTS_CACHE_TTL_MS
    );
  }

  function readStoredCounts(): StoredCounts | null {
    try {
      if (typeof window === "undefined" || !window.sessionStorage) return null;
      const raw = window.sessionStorage.getItem(COUNTS_STORAGE_KEY);
      if (!raw) return null;
      const payload = JSON.parse(raw);
      const loadedAt = Number(payload?.loadedAt || 0);
      const counts = asBroadcastCounts(payload?.counts);
      const rawEmailAvailable = payload?.emailAvailable;
      const emailAvailable = typeof rawEmailAvailable === "boolean" ? rawEmailAvailable : null;
      const audiences = Array.isArray(payload?.audiences)
        ? asBroadcastAudiences(payload.audiences)
        : null;
      if (!counts || Date.now() - loadedAt > COUNTS_DISPLAY_CACHE_TTL_MS) return null;
      return { counts, loadedAt, emailAvailable, audiences };
    } catch {
      return null;
    }
  }

  function writeStoredCounts(
    counts: BroadcastCounts,
    loadedAt: number,
    emailAvailable: boolean,
    audiences: BroadcastAudienceDescriptor[]
  ): void {
    try {
      if (typeof window === "undefined" || !window.sessionStorage) return;
      window.sessionStorage.setItem(
        COUNTS_STORAGE_KEY,
        JSON.stringify(snapshotForPayload({ counts, loadedAt, emailAvailable, audiences }))
      );
    } catch {
      // Ignore storage quota/privacy errors; in-memory counts still work.
    }
  }

  async function loadCounts({ force = false }: { force?: boolean } = {}): Promise<void> {
    let shouldLoad = false;
    updateState((s) => {
      if (!force && countsAreFresh(s)) return s;
      if (countsPromise || s.broadcastCountsLoading) return s;
      shouldLoad = true;
      return { ...s, broadcastCountsLoading: true };
    });

    if (!shouldLoad) return countsPromise || Promise.resolve();

    countsPromise = (async () => {
      try {
        const res = await api(buildAdminBroadcastAudienceCountsPath());
        if (res?.ok) {
          const payload = unwrap(res);
          const emailAvailable = Boolean(payload.email_enabled);
          const counts = asBroadcastCounts(payload.counts);
          const audiences = asBroadcastAudiences(payload.audiences);
          const options = targetOptions(audiences);
          if (!counts) {
            updateState((s) => ({
              ...s,
              broadcastEmailAvailable: emailAvailable,
              broadcastEmailAvailabilityKnown: true,
              broadcastEmailEnabled: s.broadcastEmailEnabled && emailAvailable,
              broadcastAudiencesLoaded: true,
              BROADCAST_TARGET_OPTIONS: options,
              broadcastTarget: options.some(
                (option) => option.value === s.broadcastTarget && !option.disabled
              )
                ? s.broadcastTarget
                : "all",
            }));
            return;
          }
          const loadedAt = Date.now();
          updateState((s) => ({
            ...s,
            broadcastCounts: counts,
            broadcastCountsLoadedAt: loadedAt,
            broadcastAudiencesLoaded: true,
            broadcastEmailAvailable: emailAvailable,
            broadcastEmailAvailabilityKnown: true,
            broadcastEmailEnabled: s.broadcastEmailEnabled && emailAvailable,
            BROADCAST_TARGET_OPTIONS: options,
            broadcastTarget: options.some(
              (option) => option.value === s.broadcastTarget && !option.disabled
            )
              ? s.broadcastTarget
              : "all",
          }));
          writeStoredCounts(counts, loadedAt, emailAvailable, audiences);
        }
      } catch {
        // Counts are advisory; ignore failures and keep existing/plain labels.
      } finally {
        updateState((s) => ({ ...s, broadcastCountsLoading: false }));
        countsPromise = null;
      }
    })();

    return countsPromise;
  }

  function channelsForPayload(snapshot: BroadcastState): string[] {
    const channels: string[] = [];
    if (snapshot.broadcastTelegramEnabled) channels.push("telegram");
    if (
      snapshot.broadcastEmailEnabled &&
      (!snapshot.broadcastEmailAvailabilityKnown || snapshot.broadcastEmailAvailable)
    ) {
      channels.push("email");
    }
    return channels;
  }

  function canSubmit(): boolean {
    if (state.broadcastBusy) return false;
    // One written language is enough to send: requiring all of them would
    // block a shop that serves one.
    if (
      !state.broadcastText.trim() &&
      !Object.keys(localizedForPayload(state.broadcastTexts)).length &&
      !state.broadcastImage
    )
      return false;
    if (!channelsForPayload(state).length) return false;
    if (state.broadcastScheduleEnabled) {
      const scheduledAt = new Date(state.broadcastScheduledAt);
      if (!state.broadcastScheduledAt || Number.isNaN(scheduledAt.getTime())) return false;
      if (scheduledAt.getTime() <= Date.now()) return false;
    }
    return state.broadcastButtons.every(buttonDraftValid);
  }

  /** Sends to one addressed customer, leaving the broadcast draft untouched.
   *
   * Returns ``null`` on success, or a ready-to-display error message. The
   * audience of one travels the same delivery path a broadcast does, so
   * channels, buttons and shortcodes behave identically.
   */
  async function sendToUser(input: SingleUserMessage): Promise<string | null> {
    const failure = at("user_message_failed", {}, "Message was not sent");
    try {
      const body = {
        target: `user:${Math.trunc(input.userId)}`,
        text: input.text.trim(),
        channels: input.channels,
        exclude_blocked_telegram: false,
        email_subject: input.emailSubject.trim(),
        buttons: buttonsForPayload(input.buttons),
        scheduled_at: null,
      } satisfies PostPayload<"/api/admin/broadcast">;
      const res = await api(buildAdminBroadcastPath(), {
        method: "POST",
        body: messageRequestBody(body as unknown as Record<string, unknown>, input.image),
      });
      if (res?.ok) {
        unwrap(res);
        return null;
      }
      return adminErrorMessage(res, at, failure);
    } catch {
      return failure;
    }
  }

  async function runBroadcast(): Promise<void> {
    if (!canSubmit()) {
      if (state.broadcastScheduleEnabled) {
        onToast(at("broadcast_schedule_future", {}, "The send time must be in the future"));
      }
      return;
    }
    const { target, text, texts, emailSubject, emailSubjects, buttons, channels } =
      snapshotForPayload({
        target: state.broadcastTarget,
        text: state.broadcastText,
        texts: state.broadcastTexts,
        emailSubject: state.broadcastEmailSubject,
        emailSubjects: state.broadcastEmailSubjects,
        buttons: state.broadcastButtons,
        channels: channelsForPayload(state),
      });
    updateState((s) => ({ ...s, broadcastBusy: true, broadcastResult: null }));
    const image = state.broadcastImage;

    try {
      const body = {
        target,
        text,
        texts: localizedForPayload(texts),
        channels,
        exclude_blocked_telegram: null,
        email_subject: emailSubject.trim(),
        email_subjects: localizedForPayload(emailSubjects),
        buttons: buttonsForPayload(buttons),
        scheduled_at: state.broadcastScheduleEnabled
          ? new Date(state.broadcastScheduledAt).toISOString()
          : null,
      } satisfies PostPayload<"/api/admin/broadcast">;
      const res = await api(buildAdminBroadcastPath(), {
        method: "POST",
        body: messageRequestBody(body as unknown as Record<string, unknown>, image),
      });
      if (res?.ok) {
        const payload = unwrap(res);
        updateState((s) => ({
          ...s,
          broadcastText: "",
          broadcastTexts: {},
          broadcastImage: null,
          broadcastLanguage: "",
          broadcastButtons: [],
          broadcastEmailSubject: "",
          broadcastEmailSubjects: {},
          broadcastScheduleEnabled: false,
          broadcastScheduledAt: "",
          broadcastResult: {
            queued: payload.queued || 0,
            failed: payload.failed || 0,
            emailQueued: payload.email_queued || 0,
            channels: Array.isArray(payload.channels) ? payload.channels : channels,
          },
          broadcastHistory: payload.broadcast
            ? [
                historyItemFromWire(payload.broadcast),
                ...s.broadcastHistory.filter(
                  (item) => item.broadcastId !== Number(payload.broadcast?.broadcast_id)
                ),
              ].filter((item): item is BroadcastHistoryItem => Boolean(item))
            : s.broadcastHistory,
        }));
        onToast(
          payload.broadcast?.status === "scheduled"
            ? at("broadcast_scheduled", {}, "Broadcast scheduled")
            : at("broadcast_started", {}, "Broadcast started")
        );
      } else {
        onToast(adminErrorMessage(res, at, at("broadcast_failed", {}, "Broadcast failed")));
      }
    } catch {
      onToast(at("broadcast_failed", {}, "Broadcast failed"));
    } finally {
      updateState((s) => ({ ...s, broadcastBusy: false }));
    }
  }

  async function loadHistory(): Promise<void> {
    if (historyPromise) return historyPromise;
    updateState((s) => ({ ...s, broadcastHistoryLoading: true }));
    historyPromise = (async () => {
      try {
        const response = await api(buildAdminBroadcastsPath());
        if (response?.ok) {
          const payload = unwrap(response);
          const history = Array.isArray(payload.broadcasts)
            ? payload.broadcasts
                .map(historyItemFromWire)
                .filter((item): item is BroadcastHistoryItem => Boolean(item))
            : [];
          updateState((s) => ({
            ...s,
            broadcastHistory: history,
            broadcastHistoryLoaded: true,
          }));
        }
      } catch {
        if (!state.broadcastHistoryLoaded) {
          onToast(at("broadcast_history_failed", {}, "Broadcast history could not be loaded"));
        }
      } finally {
        updateState((s) => ({ ...s, broadcastHistoryLoading: false }));
        historyPromise = null;
      }
    })();
    return historyPromise;
  }

  async function deleteBroadcast(broadcastId: number): Promise<void> {
    try {
      const response = await api(buildAdminBroadcastItemPath(broadcastId), {
        method: "DELETE",
      });
      if (response?.ok) {
        unwrap(response);
        updateState((s) => ({
          ...s,
          broadcastHistory: s.broadcastHistory.filter((item) => item.broadcastId !== broadcastId),
        }));
        onToast(at("broadcast_deleted", {}, "Broadcast removed"));
        return;
      }
      onToast(
        adminErrorMessage(
          response,
          at,
          at("broadcast_delete_failed", {}, "Broadcast could not be removed")
        )
      );
    } catch {
      onToast(at("broadcast_delete_failed", {}, "Broadcast could not be removed"));
    }
  }

  async function rescheduleBroadcast(broadcastId: number, localDateTime: string): Promise<boolean> {
    const scheduledAt = new Date(localDateTime);
    if (
      !localDateTime ||
      Number.isNaN(scheduledAt.getTime()) ||
      scheduledAt.getTime() <= Date.now()
    ) {
      onToast(at("broadcast_schedule_future", {}, "The send time must be in the future"));
      return false;
    }
    try {
      const response = await api(buildAdminBroadcastItemPath(broadcastId), {
        method: "PATCH",
        body: JSON.stringify({
          scheduled_at: scheduledAt.toISOString(),
        } satisfies PatchPayload<"/api/admin/broadcasts/{id}">),
      });
      if (response?.ok) {
        const updated = historyItemFromWire(unwrap(response));
        if (updated) {
          updateState((s) => ({
            ...s,
            broadcastHistory: s.broadcastHistory.map((item) =>
              item.broadcastId === broadcastId ? updated : item
            ),
          }));
        }
        onToast(at("broadcast_rescheduled", {}, "Scheduled time updated"));
        return true;
      }
      onToast(
        adminErrorMessage(
          response,
          at,
          at("broadcast_reschedule_failed", {}, "Scheduled time could not be updated")
        )
      );
      return false;
    } catch {
      onToast(at("broadcast_reschedule_failed", {}, "Scheduled time could not be updated"));
      return false;
    }
  }

  function updateField(fields: Partial<BroadcastState>): void {
    updateState((s) => ({ ...s, ...fields }));
  }

  async function loadShortcodes(): Promise<void> {
    if (state.broadcastShortcodesLoaded || shortcodesPromise) {
      return shortcodesPromise || Promise.resolve();
    }
    updateState((s) => ({ ...s, broadcastShortcodesLoading: true }));
    shortcodesPromise = (async () => {
      try {
        const res = await api(buildAdminBroadcastShortcodesPath());
        if (res?.ok) {
          const payload = unwrap(res);
          const shortcodes = Array.isArray(payload.shortcodes)
            ? payload.shortcodes.map((item) => ({
                name: String(item.name || ""),
                cost: String(item.cost || "db"),
                description: String(item.description || ""),
              }))
            : [];
          const allowedTags = Array.isArray(payload.allowed_tags)
            ? payload.allowed_tags.map((tag) => String(tag))
            : [];
          updateState((s) => ({
            ...s,
            broadcastShortcodes: shortcodes,
            broadcastAllowedTags: allowedTags,
            broadcastShortcodesLoaded: true,
          }));
        }
      } catch {
        // Picker is advisory; leave it empty and let the backend validate on submit.
      } finally {
        updateState((s) => ({ ...s, broadcastShortcodesLoading: false }));
        shortcodesPromise = null;
      }
    })();
    return shortcodesPromise;
  }

  async function sendPreview(
    mode: "render" | "send_telegram",
    userId: number | null = null
  ): Promise<void> {
    if (state.broadcastPreviewBusy) return;
    const written = localizedForPayload(state.broadcastTexts);
    const text =
      state.broadcastText.trim() ||
      written[state.broadcastLanguage] ||
      Object.values(written)[0] ||
      "";
    if (!text && !Object.keys(written).length && !state.broadcastImage) {
      onToast(at("broadcast_preview_empty", {}, "Enter text to preview"));
      return;
    }
    updateState((s) => ({ ...s, broadcastPreviewBusy: true }));
    try {
      const buttons = snapshotForPayload(state.broadcastButtons);
      const body = {
        text,
        texts: localizedForPayload(state.broadcastTexts),
        email_subject: state.broadcastEmailSubject.trim(),
        email_subjects: localizedForPayload(state.broadcastEmailSubjects),
        user_id: userId,
        mode,
        buttons: buttonsForPayload(buttons),
      } satisfies PostPayload<"/api/admin/broadcast/preview">;
      const res = await api(buildAdminBroadcastPreviewPath(), {
        method: "POST",
        body: messageRequestBody(body as unknown as Record<string, unknown>, state.broadcastImage),
      });
      if (res?.ok) {
        const payload = unwrap(res);
        updateState((s) => ({
          ...s,
          broadcastPreviewResult: {
            renderedText: String(payload.rendered_text || ""),
            renderedSubject:
              payload.rendered_subject == null ? null : String(payload.rendered_subject),
            unknownShortcodes: Array.isArray(payload.unknown_shortcodes)
              ? payload.unknown_shortcodes.map((code) => String(code))
              : [],
            length: Number(payload.length || 0),
            sent: Boolean(payload.sent),
          },
        }));
        if (mode === "send_telegram") {
          onToast(at("broadcast_preview_sent", {}, "Preview sent to Telegram"));
        }
      } else {
        onToast(adminErrorMessage(res, at, at("broadcast_preview_failed", {}, "Preview failed")));
      }
    } finally {
      updateState((s) => ({ ...s, broadcastPreviewBusy: false }));
    }
  }

  function addButton(): void {
    if (state.broadcastButtons.length >= MAX_BROADCAST_BUTTONS) return;
    buttonIdCounter += 1;
    updateState((s) => ({
      ...s,
      broadcastButtons: [
        ...s.broadcastButtons,
        { id: buttonIdCounter, kind: "url", label: "", url: "", promoCode: "", section: "" },
      ],
    }));
  }

  function removeButton(index: number): void {
    updateState((s) => ({
      ...s,
      broadcastButtons: s.broadcastButtons.filter((_, i) => i !== index),
    }));
  }

  function updateButton(index: number, fields: Partial<BroadcastButtonDraft>): void {
    updateState((s) => ({
      ...s,
      broadcastButtons: s.broadcastButtons.map((button, i) =>
        i === index ? { ...button, ...fields } : button
      ),
    }));
    if (fields.kind && fields.kind !== "url") {
      void loadPromoOptions();
    }
  }

  function moveButton(from: number, to: number): void {
    updateState((s) => {
      if (
        from === to ||
        from < 0 ||
        to < 0 ||
        from >= s.broadcastButtons.length ||
        to >= s.broadcastButtons.length
      ) {
        return s;
      }
      const buttons = [...s.broadcastButtons];
      const [moved] = buttons.splice(from, 1);
      buttons.splice(to, 0, moved);
      return { ...s, broadcastButtons: buttons };
    });
  }

  async function loadPromoOptions(query?: string): Promise<void> {
    const isInitialLoad = query === undefined;
    const normalizedQuery = isInitialLoad ? "" : String(query || "").trim();
    const queryKey = normalizedQuery.toLocaleLowerCase();
    promoOptionsQuery = queryKey;

    const cached = promoOptionsCache.get(queryKey);
    if (cached) {
      promoOptionsRequestId += 1;
      updateState((s) => ({
        ...s,
        broadcastPromoOptions: cached,
        broadcastPromoOptionsLoaded: true,
        broadcastPromoOptionsLoading: false,
      }));
      return;
    }

    if (!queryKey && promoOptionsPromise) return promoOptionsPromise;

    const requestId = ++promoOptionsRequestId;
    updateState((s) => ({ ...s, broadcastPromoOptionsLoading: true }));
    const request = (async () => {
      try {
        const params = normalizedQuery
          ? new URLSearchParams({ query: normalizedQuery })
          : undefined;
        const response = await api(buildAdminPromoOptionsPath(params));
        if (!isPromosListResponse(response)) {
          throw new Error("Promo suggestions request failed");
        }
        const options = promoOptionsFromResponse(response, at);
        promoOptionsCache.set(queryKey, options);
        if (requestId !== promoOptionsRequestId || promoOptionsQuery !== queryKey) return;
        updateState((s) => ({
          ...s,
          broadcastPromoOptions: options,
          broadcastPromoOptionsLoaded: true,
        }));
      } catch {
        // Suggestions are an aid only: a manually entered code is still sent
        // through the same backend validation as a selected suggestion.
        if (requestId === promoOptionsRequestId) {
          updateState((s) => ({ ...s, broadcastPromoOptionsLoaded: true }));
        }
      } finally {
        if (requestId === promoOptionsRequestId) {
          updateState((s) => ({ ...s, broadcastPromoOptionsLoading: false }));
        }
        if (!queryKey) promoOptionsPromise = null;
      }
    })();
    if (!queryKey) promoOptionsPromise = request;
    return request;
  }

  return state;
}
