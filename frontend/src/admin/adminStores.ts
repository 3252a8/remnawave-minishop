import { QueryClient } from "@tanstack/svelte-query";
import { createAdsStore } from "../lib/admin/stores/adsStore.js";
import { createBackupsStore } from "../lib/admin/stores/backupsStore.js";
import { createBroadcastStore } from "../lib/admin/stores/broadcastStore.js";
import { createHealthStore } from "../lib/admin/stores/healthStore.js";
import { createLogsStore } from "../lib/admin/stores/logsStore.js";
import { createPaymentsStore } from "../lib/admin/stores/paymentsStore.js";
import { createPromosStore } from "../lib/admin/stores/promosStore.js";
import { createSettingsStore } from "../lib/admin/stores/settingsStore.js";
import { createStatsStore } from "../lib/admin/stores/statsStore.js";
import { createAdminSupportStore } from "../lib/admin/stores/supportStore.js";
import { createTariffsStore } from "../lib/admin/stores/tariffsStore.js";
import { createThemesStore } from "../lib/admin/stores/themesStore.js";
import { createTranslationsStore } from "../lib/admin/stores/translationsStore.js";
import { createUsersStore } from "../lib/admin/stores/usersStore.js";
import { createRoleApi } from "../lib/admin/roleApi.js";
import {
  setAdsStore,
  setAdminSupportStore,
  setBackupsStore,
  setBroadcastStore,
  setHealthStore,
  setLogsStore,
  setPaymentsStore,
  setPromosStore,
  setSettingsStore,
  setStatsStore,
  setTariffsStore,
  setThemesStore,
  setTranslationsStore,
  setUsersStore,
  setRoleApi,
} from "../lib/admin/context";
import type { TariffsCatalog } from "../lib/admin/stores/tariffsStore";
import type { ApiClient } from "../lib/webapp/publicApi";

export type AdminApi = ApiClient["api"];
export type AdminApiBlob = ApiClient["apiBlob"];
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

type AdminStoresOptions = {
  api: AdminApi;
  apiBlob: AdminApiBlob;
  at: TranslateFn;
  onToast: (message: string) => void;
  onTariffsSaved: (catalog: TariffsCatalog) => void | Promise<void>;
  onThemesSaved: () => void | Promise<void>;
  routePrefix: string;
};

export function createAdminStores({
  api,
  apiBlob,
  at,
  onToast,
  onTariffsSaved,
  onThemesSaved,
  routePrefix,
}: AdminStoresOptions) {
  const adminQueryClient = new QueryClient({
    defaultOptions: {
      queries: {
        gcTime: 10 * 60 * 1000,
        retry: false,
        staleTime: 60 * 1000,
      },
    },
  });
  // Keep each store's narrower endpoint contract at this composition boundary.
  // Expanding every route into one contextual union exceeds TypeScript's
  // representable-union limit as the generated OpenAPI surface grows.
  const settingsStore = createSettingsStore({
    api: api as never,
    onToast,
    at,
    queryClient: adminQueryClient,
  });
  const adsStore = createAdsStore({ api: api as never, onToast, at });
  const backupsStore = createBackupsStore({ api: api as never, onToast, at });
  const broadcastStore = createBroadcastStore({ api: api as never, onToast, at });
  const healthStore = createHealthStore({
    api: api as never,
    at,
    queryClient: adminQueryClient,
  });
  const logsStore = createLogsStore({
    api: api as never,
    onToast,
    at,
    queryClient: adminQueryClient,
  });
  const paymentsStore = createPaymentsStore({
    api: api as never,
    onToast,
    at,
    routePrefix,
    queryClient: adminQueryClient,
  });
  const promosStore = createPromosStore({
    api: api as never,
    onToast,
    at,
    routePrefix,
    queryClient: adminQueryClient,
  });
  const statsStore = createStatsStore({
    api: api as never,
    onToast,
    at,
    queryClient: adminQueryClient,
  });
  const supportStore = createAdminSupportStore({
    api: api as never,
    apiBlob,
    onToast,
    at,
    routePrefix,
  });
  const tariffsStore = createTariffsStore({
    api: api as never,
    onTariffsSaved,
    flash: onToast,
    at,
  });
  const themesStore = createThemesStore({
    api: api as never,
    apiBlob,
    onThemesSaved,
    flash: onToast,
    at,
  });
  const translationsStore = createTranslationsStore({
    api: api as never,
    onToast,
    at,
    queryClient: adminQueryClient,
  });
  const usersStore = createUsersStore({
    api: api as never,
    onToast,
    at,
    routePrefix,
    queryClient: adminQueryClient,
  });

  setPromosStore(promosStore);
  setAdsStore(adsStore);
  setHealthStore(healthStore);
  setBackupsStore(backupsStore);
  setBroadcastStore(broadcastStore);
  setLogsStore(logsStore);
  setPaymentsStore(paymentsStore);
  setStatsStore(statsStore);
  setAdminSupportStore(supportStore);
  setSettingsStore(settingsStore);
  setUsersStore(usersStore);
  setRoleApi(createRoleApi(api as never));
  setTariffsStore(tariffsStore);
  setThemesStore(themesStore);
  setTranslationsStore(translationsStore);

  return {
    adminQueryClient,
    adsStore,
    backupsStore,
    broadcastStore,
    healthStore,
    logsStore,
    paymentsStore,
    promosStore,
    settingsStore,
    statsStore,
    supportStore,
    tariffsStore,
    themesStore,
    translationsStore,
    usersStore,
  };
}
