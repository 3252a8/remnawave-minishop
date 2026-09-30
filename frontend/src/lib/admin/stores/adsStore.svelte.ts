import { adminErrorMessage } from "../errors.js";
import {
  unwrap,
  type ApiClient,
  type PostPayload,
  buildAdminAdsPath,
  buildAdminAdPath,
  buildAdminAdTogglePath,
  buildAdminAdAssignPath,
  buildAdminAdResetStatsPath,
  buildAdminAdPurchasesPath,
} from "../../webapp/publicApi";
import type { components } from "../../api/openapi.generated";
import { snapshotForPayload } from "./snapshotForPayload.svelte";
import { defineRawStateProperty } from "./rawStateProperty";

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = ApiClient["api"];
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type Ad = components["schemas"]["AdOut"];
type AdDraft = components["schemas"]["AdCreateBody"];
type AdToggleBody = components["schemas"]["AdToggleBody"];
type AdPurchaseItem = components["schemas"]["AdPurchaseItem"];
type AdsState = {
  ads: Ad[];
  adsTotals: Record<string, number> | null;
  adsLoading: boolean;
  adCreateOpen: boolean;
  adDraft: AdDraft;
  adPurchasesOpen: boolean;
  adPurchasesLoading: boolean;
  adPurchasesList: AdPurchaseItem[];
  adPurchasesAd: Ad | null;
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
  assignAdvertiser: (ad: Ad, advertiserId: number | null) => Promise<void>;
  resetAdStats: (ad: Ad) => Promise<void>;
  loadAdPurchases: (ad: Ad) => Promise<void>;
  setPurchasesOpen: (open: boolean) => void;
  deleteAd: (ad: Ad) => Promise<void>;
  setCreateOpen: (open: boolean) => void;
  updateDraft: (fields: Partial<AdDraft>) => void;
};

function isOkResponse<T extends { ok: true }>(response: T | AdminErrorResponse): response is T {
  return response.ok === true;
}

const defaultAdDraft = (): AdDraft => ({
  source: "",
  start_param: "",
  cost: 0,
  advertiser_id: null,
});

export function createAdsStore({ api, onToast, at }: AdsStoreOptions): AdsStore {
  let ads = $state.raw<Ad[]>([]);
  const state = $state<Omit<AdsState, "ads">>({
    adsTotals: null,
    adsLoading: false,
    adCreateOpen: false,
    adDraft: defaultAdDraft(),
    adPurchasesOpen: false,
    adPurchasesLoading: false,
    adPurchasesList: [],
    adPurchasesAd: null,
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
      const data = await api(buildAdminAdsPath());
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

    const res = await api(buildAdminAdsPath(), {
      method: "POST",
      body: JSON.stringify(draft satisfies PostPayload<"/api/admin/ads">),
    });

    if (isOkResponse(res)) {
      onToast(at("ad_created", {}, "Campaign created"));
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
    const res = await api(path, {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (isOkResponse(res)) {
      ads = ads.map((c) => (c.id === ad.id ? { ...c, is_active: !ad.is_active } : c));
    } else {
      onToast(adminErrorMessage(res, at));
    }
  }

  async function assignAdvertiser(ad: Ad, advertiserId: number | null): Promise<void> {
    const path = buildAdminAdAssignPath(ad.id);
    const body: PostPayload<"/api/admin/ads/{campaign_id}/assign"> = {
      advertiser_id: advertiserId,
    };
    const res = await api(path, {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (isOkResponse(res)) {
      ads = ads.map((c) => (c.id === ad.id ? { ...c, advertiser_id: advertiserId } : c));
      onToast(at("ad_assigned", {}, "Advertiser updated"));
    } else {
      onToast(adminErrorMessage(res, at));
    }
  }

  async function resetAdStats(ad: Ad): Promise<void> {
    const path = buildAdminAdResetStatsPath(ad.id);
    const res = await api(path, {
      method: "POST",
    });
    if (isOkResponse(res)) {
      onToast(at("ad_stats_reset", {}, "Statistics reset"));
      await loadAds();
    } else {
      onToast(adminErrorMessage(res, at));
    }
  }

  async function loadAdPurchases(ad: Ad): Promise<void> {
    state.adPurchasesOpen = true;
    state.adPurchasesLoading = true;
    state.adPurchasesList = [];
    state.adPurchasesAd = ad;
    try {
      const params = new URLSearchParams({ page: "0", page_size: "50" });
      const path = buildAdminAdPurchasesPath(ad.id, params);
      const res = await api(path);
      if (isOkResponse(res)) {
        const payload = unwrap(res);
        state.adPurchasesList = payload.purchases || [];
      } else {
        onToast(adminErrorMessage(res, at));
      }
    } finally {
      state.adPurchasesLoading = false;
    }
  }

  function setPurchasesOpen(open: boolean): void {
    state.adPurchasesOpen = open;
  }

  async function deleteAd(ad: Ad): Promise<void> {
    const path = buildAdminAdPath(ad.id);
    const res = await api(path, { method: "DELETE" });
    if (isOkResponse(res)) {
      ads = ads.filter((c) => c.id !== ad.id);
      onToast(at("ad_deleted", {}, "Campaign deleted"));
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
    assignAdvertiser,
    resetAdStats,
    loadAdPurchases,
    setPurchasesOpen,
    deleteAd,
    setCreateOpen,
    updateDraft,
  });
}
