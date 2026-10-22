import { createContext } from "svelte";

import type { AccountStore } from "./stores/accountStore";
import type { ActionsStore } from "./stores/actionsStore";
import type { AuthStore } from "./stores/authStore";
import type { BillingStore } from "./stores/billingStore";
import type { DevicesStore } from "./stores/devicesStore";
import type { InstallGuidesStore } from "./stores/installGuidesStore";
import type { PublicDocumentsStore } from "./stores/publicDocumentsStore.svelte";
import type { SupportStore } from "./stores/supportStore";

export const [getAuthStore, setAuthStore] = createContext<AuthStore>();
export const [getBillingStore, setBillingStore] = createContext<BillingStore>();
export const [getDevicesStore, setDevicesStore] = createContext<DevicesStore>();
export const [getSupportStore, setSupportStore] = createContext<SupportStore>();
export const [getInstallGuidesStore, setInstallGuidesStore] = createContext<InstallGuidesStore>();
export const [getPublicDocumentsStore, setPublicDocumentsStore] =
  createContext<PublicDocumentsStore>();
export const [getActionsStore, setActionsStore] = createContext<ActionsStore>();
export const [getAccountStore, setAccountStore] = createContext<AccountStore>();
