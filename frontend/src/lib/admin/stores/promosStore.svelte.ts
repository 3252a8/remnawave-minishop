import { adminErrorMessage } from "../errors.js";
import { copyTextToClipboard } from "../../webapp/clipboard.js";
import {
  unwrap,
  type ApiResponse,
  type ApiClient,
  type GetResponse,
  type PostPayload,
  type PostResponse,
  buildAdminPromoActivationsPath,
  buildAdminPromosPath,
  buildAdminPromoPath,
} from "../../webapp/publicApi";
import type { components } from "../../api/openapi.generated";
import { snapshotForPayload } from "./snapshotForPayload.svelte";
import { defineRawStateProperty } from "./rawStateProperty";
import {
  fetchAdminQuery,
  invalidateAdminQuery,
  type AdminQueryClient,
  type AdminQueryKey,
} from "./adminQueryCache";

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = <Path extends Parameters<ApiClient["api"]>[0]>(
  path: Path,
  options?: Parameters<ApiClient["api"]>[1]
) => Promise<ApiResponse<Path> | AdminErrorResponse>;
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type Promo = components["schemas"]["PromoOut"];
type PromoActivation = components["schemas"]["PromoActivationOut"];
type PromoDraft = Omit<components["schemas"]["PromoCreateBody"], "valid_days"> & {
  valid_days: number;
};
type PromoPatch = components["schemas"]["PromoUpdateBody"];
type PromoEffectKind =
  "bonus_days" | "discount_percent" | "duration_multiplier" | "traffic_multiplier";
type PromoEffectPayload = {
  bonus_days?: number | null;
  discount_percent?: number | null;
  duration_multiplier?: number | null;
  traffic_multiplier?: number | null;
  bonus_requires_payment?: boolean | null;
};
type PromoPatchResponse = Extract<ApiResponse<"/api/admin/promos/{promo_id}">, { promo: Promo }>;
type PromoDeleteResponse = Extract<
  ApiResponse<"/api/admin/promos/{promo_id}">,
  { ok: true; promo?: never }
>;
type PromosListResponse = GetResponse<"/api/admin/promos">;
type PromoCreateResponse = PostResponse<"/api/admin/promos">;
type PromoActivationsResponse = GetResponse<"/api/admin/promos/{promo_id}/activations">;
type PromosState = {
  promos: Promo[];
  promosTotal: number;
  promosPage: number;
  promosLoading: boolean;
  promoCreateOpen: boolean;
  promoDraft: PromoDraft;
  promoEditOpen: boolean;
  promoEditing: Promo | null;
  promoEditDraft: PromoPatch;
  promoActivationsOpen: boolean;
  promoActivationsPromo: Promo | null;
  promoActivations: PromoActivation[];
  promoActivationsTotal: number;
  promoActivationsPage: number;
  promoActivationsLoading: boolean;
};
type PromosStoreOptions = {
  api: AdminApi;
  onToast: ToastFn;
  at?: TranslateFn;
  queryClient?: AdminQueryClient | null;
};
export type PromosStore = PromosState & {
  loadPromos: (options?: { refresh?: boolean }) => Promise<void>;
  createPromo: () => Promise<void>;
  savePromo: () => Promise<void>;
  togglePromo: (promo: Promo) => Promise<void>;
  deletePromo: (promo: Promo) => Promise<void>;
  openEditPromo: (promo: Promo) => void;
  closeEditPromo: () => void;
  updateEditDraft: (fields: Partial<PromoPatch>) => void;
  copyToClipboard: (text: string | null | undefined, successMessage?: string) => Promise<void>;
  openActivations: (promo: Promo) => Promise<void>;
  closeActivations: () => void;
  loadActivations: (page?: number) => Promise<void>;
  setActivationsPage: (page: number) => void;
  setPage: (page: number) => void;
  setCreateOpen: (open: boolean) => void;
  updateDraft: (fields: Partial<PromoDraft>) => void;
  PROMOS_PAGE_SIZE: number;
  ACTIVATIONS_PAGE_SIZE: number;
};

function isOkResponse<T extends { ok: true }>(response: T | AdminErrorResponse): response is T {
  return response.ok === true;
}

const PROMOS_QUERY_KEY = ["admin", "promos"] as const;
const PROMO_ACTIVATIONS_QUERY_KEY = ["admin", "promos", "activations"] as const;

class AdminPromosError extends Error {
  payload: AdminErrorResponse;

  constructor(message: string, payload: AdminErrorResponse) {
    super(message);
    this.payload = payload;
  }
}

const defaultPromoDraft = (): PromoDraft => ({
  code: "",
  bonus_days: 7,
  discount_percent: null,
  duration_multiplier: null,
  traffic_multiplier: null,
  bonus_requires_payment: false,
  applies_to: "all",
  min_subscription_months: null,
  min_traffic_gb: null,
  origin: "admin",
  max_activations: 1,
  valid_days: 30,
});

const defaultPromoPatchDraft = (): PromoPatch => ({
  is_active: null,
  bonus_days: null,
  discount_percent: null,
  duration_multiplier: null,
  traffic_multiplier: null,
  bonus_requires_payment: null,
  applies_to: null,
  min_subscription_months: null,
  min_traffic_gb: null,
  origin: null,
  max_activations: null,
  valid_until: null,
  clear_valid_until: null,
});

function promoToPatchDraft(promo: Promo): PromoPatch {
  return {
    is_active: promo.is_active,
    bonus_days: promo.bonus_days,
    discount_percent: promo.discount_percent,
    duration_multiplier: promo.duration_multiplier,
    traffic_multiplier: promo.traffic_multiplier,
    bonus_requires_payment: promo.bonus_requires_payment,
    applies_to: promo.applies_to,
    min_subscription_months: promo.min_subscription_months,
    min_traffic_gb: promo.min_traffic_gb,
    origin: promo.origin,
    max_activations: promo.max_activations,
    valid_until: promo.valid_until,
    clear_valid_until: false,
  };
}

function finiteNumber(value: number | null | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function effectKindFromPayload(payload: PromoEffectPayload): PromoEffectKind {
  if (finiteNumber(payload.bonus_days, 0) > 0) return "bonus_days";
  if (finiteNumber(payload.discount_percent, 0) > 0) return "discount_percent";
  if (finiteNumber(payload.duration_multiplier, 1) > 1) return "duration_multiplier";
  if (finiteNumber(payload.traffic_multiplier, 1) > 1) return "traffic_multiplier";
  return "bonus_days";
}

function normalizeEffectPayload<T extends PromoEffectPayload>(payload: T): T {
  const kind = effectKindFromPayload(payload);
  return {
    ...payload,
    bonus_days:
      kind === "bonus_days" ? Math.max(0, Math.trunc(finiteNumber(payload.bonus_days, 0))) : 0,
    discount_percent: kind === "discount_percent" ? payload.discount_percent : null,
    duration_multiplier: kind === "duration_multiplier" ? payload.duration_multiplier : null,
    traffic_multiplier: kind === "traffic_multiplier" ? payload.traffic_multiplier : null,
    bonus_requires_payment: kind === "bonus_days" ? Boolean(payload.bonus_requires_payment) : false,
  } as T;
}

export function createPromosStore({
  api,
  onToast,
  at = (key, _params, fallback) => fallback || key,
  queryClient = null,
}: PromosStoreOptions): PromosStore {
  let promos = $state.raw<Promo[]>([]);
  let promoActivations = $state.raw<PromoActivation[]>([]);
  const state = $state<Omit<PromosState, "promos" | "promoActivations">>({
    promosTotal: 0,
    promosPage: 0,
    promosLoading: false,
    promoCreateOpen: false,
    promoDraft: defaultPromoDraft(),
    promoEditOpen: false,
    promoEditing: null,
    promoEditDraft: defaultPromoPatchDraft(),
    promoActivationsOpen: false,
    promoActivationsPromo: null,
    promoActivationsTotal: 0,
    promoActivationsPage: 0,
    promoActivationsLoading: false,
  });
  const store = Object.create(state) as PromosStore;
  defineRawStateProperty(store, "promos", {
    get: () => promos,
    set: (value) => {
      promos = value;
    },
  });
  defineRawStateProperty(store, "promoActivations", {
    get: () => promoActivations,
    set: (value) => {
      promoActivations = value;
    },
  });

  const PROMOS_PAGE_SIZE = 25;
  const ACTIVATIONS_PAGE_SIZE = 25;

  function promosQueryKey(page: number): AdminQueryKey {
    return [
      PROMOS_QUERY_KEY[0],
      PROMOS_QUERY_KEY[1],
      {
        page,
      },
    ];
  }

  async function requestPromos(page: number): Promise<PromosListResponse> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(PROMOS_PAGE_SIZE),
    });
    const data = (await api(buildAdminPromosPath(params))) as
      PromosListResponse | AdminErrorResponse;
    if (!isOkResponse(data)) {
      throw new AdminPromosError(adminErrorMessage(data, at, "Error"), data);
    }
    return data;
  }

  function promoActivationsQueryKey(promoId: number, page: number): AdminQueryKey {
    return [
      PROMO_ACTIVATIONS_QUERY_KEY[0],
      PROMO_ACTIVATIONS_QUERY_KEY[1],
      PROMO_ACTIVATIONS_QUERY_KEY[2],
      promoId,
      page,
    ];
  }

  async function requestPromoActivations(
    promoId: number,
    page: number
  ): Promise<PromoActivationsResponse> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(ACTIVATIONS_PAGE_SIZE),
    });
    const data = (await api(buildAdminPromoActivationsPath(promoId, params))) as
      PromoActivationsResponse | AdminErrorResponse;
    if (!isOkResponse(data)) {
      throw new AdminPromosError(adminErrorMessage(data, at, "Error"), data);
    }
    return data;
  }

  function invalidatePromosQueries(): void {
    invalidateAdminQuery(queryClient, PROMOS_QUERY_KEY);
    invalidateAdminQuery(queryClient, PROMO_ACTIVATIONS_QUERY_KEY);
  }

  async function loadPromos({ refresh = false }: { refresh?: boolean } = {}): Promise<void> {
    state.promosLoading = true;
    const currentPage = state.promosPage;
    try {
      const data = await fetchAdminQuery({
        queryClient,
        queryKey: promosQueryKey(currentPage),
        queryFn: () => requestPromos(currentPage),
        refresh,
      });
      const payload = unwrap(data);
      promos = payload.promos || [];
      state.promosTotal = payload.total || 0;
    } catch (error) {
      if (error instanceof AdminPromosError) {
        onToast(adminErrorMessage(error.payload, at, "Error"));
      } else {
        onToast(error instanceof Error ? error.message : String(error || "Error"));
      }
    } finally {
      state.promosLoading = false;
    }
  }

  async function createPromo(): Promise<void> {
    const draft = normalizeEffectPayload(snapshotForPayload(state.promoDraft));

    const res = (await api(buildAdminPromosPath(), {
      method: "POST",
      body: JSON.stringify(draft satisfies PostPayload<"/api/admin/promos">),
    })) as PromoCreateResponse | AdminErrorResponse;

    if (isOkResponse(res)) {
      invalidatePromosQueries();
      onToast(at("promo_created_toast", {}, "Code created"));
      state.promoCreateOpen = false;
      state.promoDraft = defaultPromoDraft();
      await loadPromos({ refresh: true });
    } else {
      onToast(adminErrorMessage(res, at, "Error"));
    }
  }

  async function savePromo(): Promise<void> {
    const promo = snapshotForPayload(state.promoEditing);
    if (!promo) return;
    const path = buildAdminPromoPath(promo.id);
    const draft = normalizeEffectPayload(snapshotForPayload(state.promoEditDraft));
    const res = (await api(path, {
      method: "PATCH",
      body: JSON.stringify(draft),
    })) as PromoPatchResponse | AdminErrorResponse;
    if (isOkResponse(res)) {
      invalidatePromosQueries();
      const payload = unwrap(res);
      promos = promos.map((p) => (p.id === promo.id ? payload.promo : p));
      state.promoEditing = payload.promo;
      state.promoEditDraft = promoToPatchDraft(payload.promo);
      state.promoEditOpen = false;
      onToast(at("promo_saved_toast", {}, "Code saved"));
    } else {
      onToast(adminErrorMessage(res, at, "Error"));
    }
  }

  async function togglePromo(promo: Promo): Promise<void> {
    const promoSnapshot = snapshotForPayload(promo);
    const path = buildAdminPromoPath(promoSnapshot.id);
    const body = { is_active: !promoSnapshot.is_active } satisfies Partial<PromoPatch>;
    const res = (await api(path, {
      method: "PATCH",
      body: JSON.stringify(body),
    })) as PromoPatchResponse | AdminErrorResponse;
    if (isOkResponse(res)) {
      invalidatePromosQueries();
      const payload = unwrap(res);
      promos = promos.map((p) => (p.id === promo.id ? payload.promo : p));
    } else {
      onToast(adminErrorMessage(res, at, "Error"));
    }
  }

  async function deletePromo(promo: Promo): Promise<void> {
    const path = buildAdminPromoPath(promo.id);
    const res = (await api(path, { method: "DELETE" })) as PromoDeleteResponse | AdminErrorResponse;
    if (isOkResponse(res)) {
      invalidatePromosQueries();
      promos = promos.filter((p) => p.id !== promo.id);
      if (state.promoEditing?.id === promo.id) closeEditPromo();
      if (state.promoActivationsPromo?.id === promo.id) closeActivations();
      onToast(at("promo_deleted_toast", {}, "Code deleted"));
    } else {
      onToast(adminErrorMessage(res, at, "Error"));
    }
  }

  function openEditPromo(promo: Promo): void {
    state.promoEditing = promo;
    state.promoEditDraft = promoToPatchDraft(promo);
    state.promoEditOpen = true;
  }

  function closeEditPromo(): void {
    state.promoEditOpen = false;
    state.promoEditing = null;
    state.promoEditDraft = defaultPromoPatchDraft();
  }

  function updateEditDraft(fields: Partial<PromoPatch>): void {
    state.promoEditDraft = { ...state.promoEditDraft, ...fields };
  }

  async function copyToClipboard(
    text: string | null | undefined,
    successMessage = at("link_copied", {}, "Скопировано")
  ): Promise<void> {
    if (!text) return;
    await copyTextToClipboard(text);
    onToast(successMessage);
  }

  async function openActivations(promo: Promo): Promise<void> {
    state.promoActivationsPromo = promo;
    state.promoActivationsOpen = true;
    state.promoActivationsPage = 0;
    await loadActivations(0);
  }

  function closeActivations(): void {
    state.promoActivationsOpen = false;
    state.promoActivationsPromo = null;
    promoActivations = [];
    state.promoActivationsTotal = 0;
    state.promoActivationsPage = 0;
  }

  async function loadActivations(page = state.promoActivationsPage): Promise<void> {
    const promo = state.promoActivationsPromo;
    if (!promo) return;
    state.promoActivationsLoading = true;
    state.promoActivationsPage = page;
    try {
      const data = await fetchAdminQuery({
        queryClient,
        queryKey: promoActivationsQueryKey(promo.id, page),
        queryFn: () => requestPromoActivations(promo.id, page),
      });
      const payload = unwrap(data);
      promoActivations = payload.activations || [];
      state.promoActivationsTotal = payload.total || 0;
    } catch (error) {
      if (error instanceof AdminPromosError) {
        onToast(adminErrorMessage(error.payload, at, "Error"));
      } else {
        onToast(error instanceof Error ? error.message : String(error || "Error"));
      }
    } finally {
      state.promoActivationsLoading = false;
    }
  }

  function setActivationsPage(page: number): void {
    void loadActivations(page);
  }

  function setPage(page: number): void {
    state.promosPage = page;
    void loadPromos();
  }

  function setCreateOpen(open: boolean): void {
    state.promoCreateOpen = open;
  }

  function updateDraft(fields: Partial<PromoDraft>): void {
    state.promoDraft = { ...state.promoDraft, ...fields };
  }

  return Object.assign(store, {
    loadPromos,
    createPromo,
    savePromo,
    togglePromo,
    deletePromo,
    openEditPromo,
    closeEditPromo,
    updateEditDraft,
    copyToClipboard,
    openActivations,
    closeActivations,
    loadActivations,
    setActivationsPage,
    setPage,
    setCreateOpen,
    updateDraft,
    PROMOS_PAGE_SIZE,
    ACTIVATIONS_PAGE_SIZE,
  });
}
