import { writable, type Writable } from "svelte/store";
import { adminErrorMessage } from "../errors.js";
import {
  unwrap,
  type ApiResponse,
  type GetResponse,
  type PostPayload,
  type PostResponse,
} from "../../webapp/publicApi";
import type { components } from "../../api/openapi.generated";

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = <Path extends string>(
  path: Path,
  options?: RequestInit
) => Promise<ApiResponse<Path> | AdminErrorResponse>;
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type Promo = components["schemas"]["PromoOut"];
type PromoDraft = Omit<components["schemas"]["PromoCreateBody"], "valid_days"> & {
  valid_days: number;
};
type PromoPatch = components["schemas"]["PromoUpdateBody"];
type PromoDetailPath = "/api/admin/promos/{promo_id}";
type PromoPatchResponse = Extract<ApiResponse<PromoDetailPath>, { promo: Promo }>;
type PromoDeleteResponse = Extract<ApiResponse<PromoDetailPath>, { ok: true; promo?: never }>;
type PromosListResponse = GetResponse<"/api/admin/promos">;
type PromoCreateResponse = PostResponse<"/api/admin/promos">;
type PromosState = {
  promos: Promo[];
  promosTotal: number;
  promosPage: number;
  promosLoading: boolean;
  promoCreateOpen: boolean;
  promoDraft: PromoDraft;
};
type PromosStoreOptions = {
  api: AdminApi;
  onToast: ToastFn;
  at?: TranslateFn;
};
export type PromosStore = Writable<PromosState> & {
  loadPromos: () => Promise<void>;
  createPromo: () => Promise<void>;
  togglePromo: (promo: Promo) => Promise<void>;
  deletePromo: (promo: Promo) => Promise<void>;
  setPage: (page: number) => void;
  setCreateOpen: (open: boolean) => void;
  updateDraft: (fields: Partial<PromoDraft>) => void;
  PROMOS_PAGE_SIZE: number;
};

function isOkResponse<T extends { ok: true }>(response: T | AdminErrorResponse): response is T {
  return response.ok === true;
}

const defaultPromoDraft = (): PromoDraft => ({
  code: "",
  bonus_days: 7,
  max_activations: 1,
  valid_days: 30,
});

export function createPromosStore({
  api,
  onToast,
  at = (key, _params, fallback) => fallback || key,
}: PromosStoreOptions): PromosStore {
  const state: Writable<PromosState> = writable({
    promos: [],
    promosTotal: 0,
    promosPage: 0,
    promosLoading: false,
    promoCreateOpen: false,
    promoDraft: defaultPromoDraft(),
  });

  const PROMOS_PAGE_SIZE = 25;

  async function loadPromos(): Promise<void> {
    state.update((s) => ({ ...s, promosLoading: true }));
    let currentPage = 0;
    state.update((s) => {
      currentPage = s.promosPage;
      return s;
    });
    try {
      const data = (await api(
        `/admin/promos?page=${currentPage}&page_size=${PROMOS_PAGE_SIZE}`
      )) as PromosListResponse | AdminErrorResponse;
      if (isOkResponse(data)) {
        const payload = unwrap(data);
        state.update((s) => ({
          ...s,
          promos: payload.promos || [],
          promosTotal: payload.total || 0,
        }));
      }
    } finally {
      state.update((s) => ({ ...s, promosLoading: false }));
    }
  }

  async function createPromo(): Promise<void> {
    let draft: PromoDraft = defaultPromoDraft();
    state.update((s) => {
      draft = s.promoDraft;
      return s;
    });
    if (!draft.code.trim()) return;

    const res = (await api("/admin/promos", {
      method: "POST",
      body: JSON.stringify(draft satisfies PostPayload<"/api/admin/promos">),
    })) as PromoCreateResponse | AdminErrorResponse;

    if (isOkResponse(res)) {
      onToast("Промокод создан");
      state.update((s) => ({
        ...s,
        promoCreateOpen: false,
        promoDraft: defaultPromoDraft(),
      }));
      await loadPromos();
    } else {
      onToast(adminErrorMessage(res, at, "Ошибка"));
    }
  }

  async function togglePromo(promo: Promo): Promise<void> {
    const path = `/admin/promos/${promo.id}` as PromoDetailPath;
    const body = { is_active: !promo.is_active } satisfies Partial<PromoPatch>;
    const res = (await api(path, {
      method: "PATCH",
      body: JSON.stringify(body),
    })) as PromoPatchResponse | AdminErrorResponse;
    if (isOkResponse(res)) {
      const payload = unwrap(res);
      state.update((s) => ({
        ...s,
        promos: s.promos.map((p) => (p.id === promo.id ? payload.promo : p)),
      }));
    } else {
      onToast(adminErrorMessage(res, at, "Ошибка"));
    }
  }

  async function deletePromo(promo: Promo): Promise<void> {
    const path = `/admin/promos/${promo.id}` as PromoDetailPath;
    const res = (await api(path, { method: "DELETE" })) as PromoDeleteResponse | AdminErrorResponse;
    if (isOkResponse(res)) {
      state.update((s) => ({
        ...s,
        promos: s.promos.filter((p) => p.id !== promo.id),
      }));
      onToast("Промокод удалён");
    } else {
      onToast(adminErrorMessage(res, at, "Ошибка"));
    }
  }

  function setPage(page: number): void {
    state.update((s) => ({ ...s, promosPage: page }));
    loadPromos();
  }

  function setCreateOpen(open: boolean): void {
    state.update((s) => ({ ...s, promoCreateOpen: open }));
  }

  function updateDraft(fields: Partial<PromoDraft>): void {
    state.update((s) => ({ ...s, promoDraft: { ...s.promoDraft, ...fields } }));
  }

  return {
    subscribe: state.subscribe,
    set: state.set,
    update: state.update,
    loadPromos,
    createPromo,
    togglePromo,
    deletePromo,
    setPage,
    setCreateOpen,
    updateDraft,
    PROMOS_PAGE_SIZE,
  };
}
