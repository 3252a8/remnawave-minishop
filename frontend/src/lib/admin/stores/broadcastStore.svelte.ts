import { adminErrorMessage } from "../errors.js";
import {
  buildAdminBroadcastAudienceCountsPath,
  buildAdminBroadcastPath,
  buildAdminBroadcastPreviewPath,
  buildAdminBroadcastShortcodesPath,
  buildAdminPromosPath,
  unwrap,
  type ApiClient,
  type ApiResponse,
  type GetResponse,
  type PostPayload,
} from "../../webapp/publicApi";
import type { components } from "../../api/openapi.generated";
import { snapshotForPayload } from "./snapshotForPayload.svelte";

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = <Path extends Parameters<ApiClient["api"]>[0]>(
  path: Path,
  options?: Parameters<ApiClient["api"]>[1]
) => Promise<ApiResponse<Path> | AdminErrorResponse>;
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type BroadcastCounts = Record<string, number>;
type BroadcastResult = { queued: number; failed: number; emailQueued: number; channels: string[] };
type BroadcastTargetOption = { value: string; label: string };
type StoredCounts = { counts: BroadcastCounts; loadedAt: number; emailAvailable: boolean | null };
export type BroadcastButtonKind = "url" | "promo_bot" | "promo_webapp";
export type BroadcastButtonDraft = {
  id: number;
  kind: BroadcastButtonKind;
  label: string;
  url: string;
  promoCode: string;
};
export type BroadcastPromoOption = { value: string; label: string };
export type BroadcastShortcodeInfo = { name: string; cost: string; description: string };
export type BroadcastPreviewResult = {
  renderedText: string;
  renderedSubject: string | null;
  unknownShortcodes: string[];
  length: number;
  sent: boolean;
};
export type BroadcastState = {
  broadcastTarget: string;
  broadcastText: string;
  broadcastBusy: boolean;
  broadcastResult: BroadcastResult | null;
  broadcastCounts: BroadcastCounts | null;
  broadcastCountsLoading: boolean;
  broadcastCountsLoadedAt: number;
  broadcastTelegramEnabled: boolean;
  broadcastEmailEnabled: boolean;
  broadcastEmailAvailable: boolean;
  broadcastEmailAvailabilityKnown: boolean;
  broadcastEmailSubject: string;
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
  loadPromoOptions: () => Promise<void>;
  loadShortcodes: () => Promise<void>;
  sendPreview: (mode: "render" | "send_telegram", userId?: number | null) => Promise<void>;
  canSubmit: () => boolean;
  BROADCAST_TARGET_OPTIONS: BroadcastTargetOption[];
  MAX_BROADCAST_BUTTONS: number;
};

export const MAX_BROADCAST_BUTTONS = 4;

function buttonDraftValid(button: BroadcastButtonDraft): boolean {
  if (!button.label.trim() || button.label.trim().length > 64) return false;
  if (button.kind === "url") {
    const url = button.url.trim().toLowerCase();
    return url.startsWith("https://") || url.startsWith("http://");
  }
  return /^[A-Za-z0-9_-]{1,58}$/.test(button.promoCode.trim());
}

function buttonsForPayload(buttons: BroadcastButtonDraft[]) {
  return buttons.map((button) => ({
    kind: button.kind,
    label: button.label.trim(),
    url: button.kind === "url" ? button.url.trim() : "",
    promo_code: button.kind === "url" ? "" : button.promoCode.trim(),
  }));
}

type PromoListItem = components["schemas"]["PromoOut"];
type PromosListResponse = GetResponse<"/api/admin/promos">;

// Only codes a user can still redeem belong in the button dropdown.
function promoUsable(promo: PromoListItem): boolean {
  if (!promo.is_active) return false;
  const validUntil = promo.valid_until ? Date.parse(String(promo.valid_until)) : NaN;
  if (Number.isFinite(validUntil) && validUntil <= Date.now()) return false;
  const max = Number(promo.max_activations);
  const current = Number(promo.current_activations);
  if (Number.isFinite(max) && max > 0 && Number.isFinite(current) && current >= max) return false;
  return true;
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

function asBroadcastCounts(value: unknown): BroadcastCounts | null {
  if (!value || typeof value !== "object") return null;
  return Object.fromEntries(
    Object.entries(value).map(([key, count]) => {
      const numericCount = Number(count);
      return [key, Number.isFinite(numericCount) ? numericCount : 0];
    })
  );
}

export function createBroadcastStore({ api, onToast, at }: BroadcastStoreOptions): BroadcastStore {
  const COUNTS_CACHE_TTL_MS = 30_000;
  const COUNTS_DISPLAY_CACHE_TTL_MS = 5 * 60_000;
  const COUNTS_STORAGE_KEY = "remnawave-admin:broadcast-audience-counts";
  let countsPromise: Promise<void> | null = null;
  let promoOptionsPromise: Promise<void> | null = null;
  let shortcodesPromise: Promise<void> | null = null;
  let buttonIdCounter = 0;
  const cachedCounts = readStoredCounts();

  const state = $state<BroadcastStore>({
    broadcastTarget: "all",
    broadcastText: "",
    broadcastBusy: false,
    broadcastResult: null,
    broadcastCounts: cachedCounts?.counts || null,
    broadcastCountsLoading: false,
    broadcastCountsLoadedAt: cachedCounts?.loadedAt || 0,
    broadcastTelegramEnabled: true,
    broadcastEmailEnabled: false,
    broadcastEmailAvailable: cachedCounts?.emailAvailable ?? false,
    broadcastEmailAvailabilityKnown: typeof cachedCounts?.emailAvailable === "boolean",
    broadcastEmailSubject: "",
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
    canSubmit,
    BROADCAST_TARGET_OPTIONS: [],
    MAX_BROADCAST_BUTTONS,
  });

  function updateState(updater: (snapshot: BroadcastStore) => BroadcastStore): void {
    const next = updater(state);
    if (next === state) return;
    Object.assign(state, next);
  }

  const BROADCAST_TARGET_OPTIONS: BroadcastTargetOption[] = [
    { value: "all", label: at("broadcast_target_all", {}, "All active") },
    { value: "active", label: at("broadcast_target_active", {}, "With subscription") },
    { value: "inactive", label: at("broadcast_target_inactive", {}, "No subscription") },
    { value: "expired", label: at("broadcast_target_expired", {}, "Expired subscription") },
    {
      value: "active_never_connected",
      label: at(
        "broadcast_target_active_never_connected",
        {},
        "With subscription, no VPN connections"
      ),
    },
    {
      value: "never",
      label: at("broadcast_target_never", {}, "No subscription, no history"),
    },
    {
      value: "admins",
      label: at("broadcast_target_admins", {}, "Administrators (broadcast test)"),
    },
  ];
  state.BROADCAST_TARGET_OPTIONS = BROADCAST_TARGET_OPTIONS;

  function countsAreFresh(stateSnapshot: BroadcastState): boolean {
    return Boolean(
      stateSnapshot.broadcastCounts &&
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
      if (!counts || Date.now() - loadedAt > COUNTS_DISPLAY_CACHE_TTL_MS) return null;
      return { counts, loadedAt, emailAvailable };
    } catch {
      return null;
    }
  }

  function writeStoredCounts(
    counts: BroadcastCounts,
    loadedAt: number,
    emailAvailable: boolean
  ): void {
    try {
      if (typeof window === "undefined" || !window.sessionStorage) return;
      window.sessionStorage.setItem(
        COUNTS_STORAGE_KEY,
        JSON.stringify(snapshotForPayload({ counts, loadedAt, emailAvailable }))
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
          if (!counts) {
            updateState((s) => ({
              ...s,
              broadcastEmailAvailable: emailAvailable,
              broadcastEmailAvailabilityKnown: true,
              broadcastEmailEnabled: s.broadcastEmailEnabled && emailAvailable,
            }));
            return;
          }
          const loadedAt = Date.now();
          updateState((s) => ({
            ...s,
            broadcastCounts: counts,
            broadcastCountsLoadedAt: loadedAt,
            broadcastEmailAvailable: emailAvailable,
            broadcastEmailAvailabilityKnown: true,
            broadcastEmailEnabled: s.broadcastEmailEnabled && emailAvailable,
          }));
          writeStoredCounts(counts, loadedAt, emailAvailable);
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
    if (!state.broadcastText.trim()) return false;
    if (!channelsForPayload(state).length) return false;
    return state.broadcastButtons.every(buttonDraftValid);
  }

  async function runBroadcast(): Promise<void> {
    const { target, text, emailSubject, buttons, channels } = snapshotForPayload({
      target: state.broadcastTarget,
      text: state.broadcastText,
      emailSubject: state.broadcastEmailSubject,
      buttons: state.broadcastButtons,
      channels: channelsForPayload(state),
    });
    updateState((s) => ({ ...s, broadcastBusy: true, broadcastResult: null }));

    try {
      const body = {
        target,
        text,
        channels,
        email_subject: emailSubject.trim(),
        buttons: buttonsForPayload(buttons),
      } satisfies PostPayload<"/api/admin/broadcast">;
      const res = await api(buildAdminBroadcastPath(), {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (res?.ok) {
        const payload = unwrap(res);
        updateState((s) => ({
          ...s,
          broadcastText: "",
          broadcastButtons: [],
          broadcastEmailSubject: "",
          broadcastResult: {
            queued: payload.queued || 0,
            failed: payload.failed || 0,
            emailQueued: payload.email_queued || 0,
            channels: Array.isArray(payload.channels) ? payload.channels : channels,
          },
        }));
        onToast(at("broadcast_started", {}, "Broadcast started"));
      } else {
        onToast(adminErrorMessage(res, at, at("broadcast_failed", {}, "Broadcast failed")));
      }
    } finally {
      updateState((s) => ({ ...s, broadcastBusy: false }));
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
    const text = state.broadcastText.trim();
    if (!text) {
      onToast(at("broadcast_preview_empty", {}, "Enter text to preview"));
      return;
    }
    updateState((s) => ({ ...s, broadcastPreviewBusy: true }));
    try {
      const buttons = snapshotForPayload(state.broadcastButtons);
      const body = {
        text,
        email_subject: state.broadcastEmailSubject.trim(),
        user_id: userId,
        mode,
        buttons: buttonsForPayload(buttons),
      } satisfies PostPayload<"/api/admin/broadcast/preview">;
      const res = await api(buildAdminBroadcastPreviewPath(), {
        method: "POST",
        body: JSON.stringify(body),
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
        { id: buttonIdCounter, kind: "url", label: "", url: "", promoCode: "" },
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

  async function loadPromoOptions(): Promise<void> {
    if (state.broadcastPromoOptionsLoaded || promoOptionsPromise) {
      return promoOptionsPromise || Promise.resolve();
    }
    updateState((s) => ({ ...s, broadcastPromoOptionsLoading: true }));
    promoOptionsPromise = (async () => {
      try {
        const params = new URLSearchParams({ page: "0", page_size: "100" });
        const res = await api(buildAdminPromosPath(params));
        if (isPromosListResponse(res)) {
          const promos = res.promos || [];
          const options = promos
            .filter(promoUsable)
            .map((promo) => ({ value: String(promo.code || ""), label: promoOptionLabel(promo) }))
            .filter((option) => option.value);
          updateState((s) => ({
            ...s,
            broadcastPromoOptions: options,
            broadcastPromoOptionsLoaded: true,
          }));
        }
      } catch {
        // Leave options empty; the dropdown shows the "no codes" hint and the
        // backend still validates codes on submit.
      } finally {
        updateState((s) => ({ ...s, broadcastPromoOptionsLoading: false }));
        promoOptionsPromise = null;
      }
    })();
    return promoOptionsPromise;
  }

  return state;
}
