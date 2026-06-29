import { adminErrorMessage } from "../errors.js";
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
};
export type PromosStore = PromosState & {
  loadPromos: () => Promise<void>;
  createPromo: () => Promise<void>;
  savePromo: () => Promise<void>;
  togglePromo: (promo: Promo) => Promise<void>;
  deletePromo: (promo: Promo) => Promise<void>;
  openEditPromo: (promo: Promo) => void;
  closeEditPromo: () => void;
  updateEditDraft: (fields: Partial<PromoPatch>) => void;
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

const defaultPromoDraft = (): PromoDraft => ({
  code: "",
  bonus_days: 7,
  discount_percent: null,
  duration_multiplier: null,
  traffic_multiplier: null,
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
    applies_to: promo.applies_to,
    min_subscription_months: promo.min_subscription_months,
    min_traffic_gb: promo.min_traffic_gb,
    origin: promo.origin,
    max_activations: promo.max_activations,
    valid_until: promo.valid_until,
    clear_valid_until: false,
  };
}

export function createPromosStore({
  api,
  onToast,
  at = (key, _params, fallback) => fallback || key,
}: PromosStoreOptions): PromosStore {
  const state = $state<PromosState>({
    promos: [],
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
    promoActivations: [],
    promoActivationsTotal: 0,
    promoActivationsPage: 0,
    promoActivationsLoading: false,
  });

  const PROMOS_PAGE_SIZE = 25;
  const ACTIVATIONS_PAGE_SIZE = 25;

  async function loadPromos(): Promise<void> {
    state.promosLoading = true;
    const currentPage = state.promosPage;
    try {
      const params = new URLSearchParams({
        page: String(currentPage),
        page_size: String(PROMOS_PAGE_SIZE),
      });
      const data = (await api(buildAdminPromosPath(params))) as
        PromosListResponse | AdminErrorResponse;
      if (isOkResponse(data)) {
        const payload = unwrap(data);
        state.promos = payload.promos || [];
        state.promosTotal = payload.total || 0;
      }
    } finally {
      state.promosLoading = false;
    }
  }

  async function createPromo(): Promise<void> {
    const draft = state.promoDraft;

    const res = (await api(buildAdminPromosPath(), {
      method: "POST",
      body: JSON.stringify(draft satisfies PostPayload<"/api/admin/promos">),
    })) as PromoCreateResponse | AdminErrorResponse;

    if (isOkResponse(res)) {
      onToast(at("promo_created_toast", {}, "Code created"));
      state.promoCreateOpen = false;
      state.promoDraft = defaultPromoDraft();
      await loadPromos();
    } else {
      onToast(adminErrorMessage(res, at, "Error"));
    }
  }

  async function savePromo(): Promise<void> {
    const promo = state.promoEditing;
    if (!promo) return;
    const path = buildAdminPromoPath(promo.id);
    const res = (await api(path, {
      method: "PATCH",
      body: JSON.stringify(state.promoEditDraft),
    })) as PromoPatchResponse | AdminErrorResponse;
    if (isOkResponse(res)) {
      const payload = unwrap(res);
      state.promos = state.promos.map((p) => (p.id === promo.id ? payload.promo : p));
      state.promoEditing = payload.promo;
      state.promoEditDraft = promoToPatchDraft(payload.promo);
      state.promoEditOpen = false;
      onToast(at("promo_saved_toast", {}, "Code saved"));
    } else {
      onToast(adminErrorMessage(res, at, "Error"));
    }
  }

  async function togglePromo(promo: Promo): Promise<void> {
    const path = buildAdminPromoPath(promo.id);
    const body = { is_active: !promo.is_active } satisfies Partial<PromoPatch>;
    const res = (await api(path, {
      method: "PATCH",
      body: JSON.stringify(body),
    })) as PromoPatchResponse | AdminErrorResponse;
    if (isOkResponse(res)) {
      const payload = unwrap(res);
      state.promos = state.promos.map((p) => (p.id === promo.id ? payload.promo : p));
    } else {
      onToast(adminErrorMessage(res, at, "Error"));
    }
  }

  async function deletePromo(promo: Promo): Promise<void> {
    const path = buildAdminPromoPath(promo.id);
    const res = (await api(path, { method: "DELETE" })) as PromoDeleteResponse | AdminErrorResponse;
    if (isOkResponse(res)) {
      state.promos = state.promos.filter((p) => p.id !== promo.id);
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

  async function openActivations(promo: Promo): Promise<void> {
    state.promoActivationsPromo = promo;
    state.promoActivationsOpen = true;
    state.promoActivationsPage = 0;
    await loadActivations(0);
  }

  function closeActivations(): void {
    state.promoActivationsOpen = false;
    state.promoActivationsPromo = null;
    state.promoActivations = [];
    state.promoActivationsTotal = 0;
    state.promoActivationsPage = 0;
  }

  async function loadActivations(page = state.promoActivationsPage): Promise<void> {
    const promo = state.promoActivationsPromo;
    if (!promo) return;
    state.promoActivationsLoading = true;
    state.promoActivationsPage = page;
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(ACTIVATIONS_PAGE_SIZE),
      });
      const data = (await api(buildAdminPromoActivationsPath(promo.id, params))) as
        PromoActivationsResponse | AdminErrorResponse;
      if (isOkResponse(data)) {
        const payload = unwrap(data);
        state.promoActivations = payload.activations || [];
        state.promoActivationsTotal = payload.total || 0;
      } else {
        onToast(adminErrorMessage(data, at, "Error"));
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

  return Object.assign(state, {
    loadPromos,
    createPromo,
    savePromo,
    togglePromo,
    deletePromo,
    openEditPromo,
    closeEditPromo,
    updateEditDraft,
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
