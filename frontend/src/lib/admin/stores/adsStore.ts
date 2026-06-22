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
type Ad = components["schemas"]["AdOut"];
type AdDraft = components["schemas"]["AdCreateBody"];
type AdToggleBody = components["schemas"]["AdToggleBody"];
type AdsListResponse = GetResponse<"/api/admin/ads">;
type AdCreateResponse = PostResponse<"/api/admin/ads">;
type AdDeleteResponse = Extract<ApiResponse<"/api/admin/ads/{campaign_id}">, { ok: true }>;
type AdToggleResponse = Extract<ApiResponse<"/api/admin/ads/{campaign_id}/toggle">, { ok: true }>;
type AdsState = {
  ads: Ad[];
  adsTotals: Record<string, number> | null;
  adsLoading: boolean;
  adCreateOpen: boolean;
  adDraft: AdDraft;
};
type AdsStoreOptions = {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
};
export type AdsStore = Writable<AdsState> & {
  loadAds: () => Promise<void>;
  createAd: () => Promise<void>;
  toggleAd: (ad: Ad) => Promise<void>;
  deleteAd: (ad: Ad) => Promise<void>;
  setCreateOpen: (open: boolean) => void;
  updateDraft: (fields: Partial<AdDraft>) => void;
};

function isOkResponse<T extends { ok: true }>(response: T | AdminErrorResponse): response is T {
  return response.ok === true;
}

const defaultAdDraft = (): AdDraft => ({ source: "", start_param: "", cost: 0 });

export function createAdsStore({ api, onToast, at }: AdsStoreOptions): AdsStore {
  const state: Writable<AdsState> = writable({
    ads: [],
    adsTotals: null,
    adsLoading: false,
    adCreateOpen: false,
    adDraft: defaultAdDraft(),
  });

  async function loadAds(): Promise<void> {
    state.update((s) => ({ ...s, adsLoading: true }));
    try {
      const data = (await api("/admin/ads")) as AdsListResponse | AdminErrorResponse;
      if (isOkResponse(data)) {
        const payload = unwrap(data);
        state.update((s) => ({
          ...s,
          ads: payload.campaigns || [],
          adsTotals: payload.totals || {},
        }));
      }
    } finally {
      state.update((s) => ({ ...s, adsLoading: false }));
    }
  }

  async function createAd(): Promise<void> {
    let draft: AdDraft = defaultAdDraft();
    state.update((s) => {
      draft = s.adDraft;
      return s;
    });
    if (!draft.source.trim() || !draft.start_param.trim()) return;

    const res = (await api("/admin/ads", {
      method: "POST",
      body: JSON.stringify(draft satisfies PostPayload<"/api/admin/ads">),
    })) as AdCreateResponse | AdminErrorResponse;

    if (isOkResponse(res)) {
      onToast(at("ad_created", {}, "Кампания создана"));
      state.update((s) => ({
        ...s,
        adCreateOpen: false,
        adDraft: defaultAdDraft(),
      }));
      await loadAds();
    } else {
      onToast(adminErrorMessage(res, at));
    }
  }

  async function toggleAd(ad: Ad): Promise<void> {
    const path = `/admin/ads/${ad.id}/toggle` as "/api/admin/ads/{campaign_id}/toggle";
    const body = { is_active: !ad.is_active } satisfies Partial<AdToggleBody>;
    const res = (await api(path, {
      method: "POST",
      body: JSON.stringify(body),
    })) as AdToggleResponse | AdminErrorResponse;
    if (isOkResponse(res)) {
      state.update((s) => ({
        ...s,
        ads: s.ads.map((c) => (c.id === ad.id ? { ...c, is_active: !ad.is_active } : c)),
      }));
    } else {
      onToast(adminErrorMessage(res, at));
    }
  }

  async function deleteAd(ad: Ad): Promise<void> {
    const path = `/admin/ads/${ad.id}` as "/api/admin/ads/{campaign_id}";
    const res = (await api(path, { method: "DELETE" })) as AdDeleteResponse | AdminErrorResponse;
    if (isOkResponse(res)) {
      state.update((s) => ({
        ...s,
        ads: s.ads.filter((c) => c.id !== ad.id),
      }));
      onToast(at("ad_deleted", {}, "Кампания удалена"));
    } else {
      onToast(adminErrorMessage(res, at));
    }
  }

  function setCreateOpen(open: boolean): void {
    state.update((s) => ({ ...s, adCreateOpen: open }));
  }

  function updateDraft(fields: Partial<AdDraft>): void {
    state.update((s) => ({ ...s, adDraft: { ...s.adDraft, ...fields } }));
  }

  return {
    subscribe: state.subscribe,
    set: state.set,
    update: state.update,
    loadAds,
    createAd,
    toggleAd,
    deleteAd,
    setCreateOpen,
    updateDraft,
  };
}
