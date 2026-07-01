import { adminErrorMessage } from "../errors.js";
import {
  unwrap,
  type ApiResponse,
  type ApiClient,
  type GetResponse,
  type PostPayload,
  type PostResponse,
  buildAdminAdsPath,
  buildAdminAdPath,
  buildAdminAdTogglePath,
} from "../../webapp/publicApi";
import type { components } from "../../api/openapi.generated";
import { snapshotForPayload } from "./snapshotForPayload.svelte";
import { defineRawStateProperty } from "./rawStateProperty";

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = <Path extends Parameters<ApiClient["api"]>[0]>(
  path: Path,
  options?: Parameters<ApiClient["api"]>[1]
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
export type AdsStore = AdsState & {
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
  let ads = $state.raw<Ad[]>([]);
  const state = $state<Omit<AdsState, "ads">>({
    adsTotals: null,
    adsLoading: false,
    adCreateOpen: false,
    adDraft: defaultAdDraft(),
  });
  const store = Object.create(state) as AdsStore;
  defineRawStateProperty(store, "ads", {
    get: () => ads,
    set: (value) => {
      ads = value;
    },
  });

  async function loadAds(): Promise<void> {
    state.adsLoading = true;
    try {
      const data = (await api(buildAdminAdsPath())) as AdsListResponse | AdminErrorResponse;
      if (isOkResponse(data)) {
        const payload = unwrap(data);
        ads = payload.campaigns || [];
        state.adsTotals = payload.totals || {};
      }
    } finally {
      state.adsLoading = false;
    }
  }

  async function createAd(): Promise<void> {
    const draft = snapshotForPayload(state.adDraft);
    if (!draft.source.trim() || !draft.start_param.trim()) return;

    const res = (await api(buildAdminAdsPath(), {
      method: "POST",
      body: JSON.stringify(draft satisfies PostPayload<"/api/admin/ads">),
    })) as AdCreateResponse | AdminErrorResponse;

    if (isOkResponse(res)) {
      onToast(at("ad_created", {}, "Кампания создана"));
      state.adCreateOpen = false;
      state.adDraft = defaultAdDraft();
      await loadAds();
    } else {
      onToast(adminErrorMessage(res, at));
    }
  }

  async function toggleAd(ad: Ad): Promise<void> {
    const adSnapshot = snapshotForPayload(ad);
    const path = buildAdminAdTogglePath(adSnapshot.id);
    const body = { is_active: !adSnapshot.is_active } satisfies Partial<AdToggleBody>;
    const res = (await api(path, {
      method: "POST",
      body: JSON.stringify(body),
    })) as AdToggleResponse | AdminErrorResponse;
    if (isOkResponse(res)) {
      ads = ads.map((c) => (c.id === ad.id ? { ...c, is_active: !ad.is_active } : c));
    } else {
      onToast(adminErrorMessage(res, at));
    }
  }

  async function deleteAd(ad: Ad): Promise<void> {
    const path = buildAdminAdPath(ad.id);
    const res = (await api(path, { method: "DELETE" })) as AdDeleteResponse | AdminErrorResponse;
    if (isOkResponse(res)) {
      ads = ads.filter((c) => c.id !== ad.id);
      onToast(at("ad_deleted", {}, "Кампания удалена"));
    } else {
      onToast(adminErrorMessage(res, at));
    }
  }

  function setCreateOpen(open: boolean): void {
    state.adCreateOpen = open;
  }

  function updateDraft(fields: Partial<AdDraft>): void {
    state.adDraft = { ...state.adDraft, ...fields };
  }

  return Object.assign(store, {
    loadAds,
    createAd,
    toggleAd,
    deleteAd,
    setCreateOpen,
    updateDraft,
  });
}
