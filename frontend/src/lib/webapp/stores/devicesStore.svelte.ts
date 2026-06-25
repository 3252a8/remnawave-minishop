import type { ApiClient, DevicesResponse, PostPayload } from "../publicApi";
import { unwrap } from "../publicApi";

type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type DeviceRecord = Record<string, unknown>;
export type DevicesState = {
  devicesData: DevicesResponse | null;
  devicesLoaded: boolean;
  devicesBusy: boolean;
  devicesStatus: string;
  devicesIsError: boolean;
  devicesErrorCode: string;
  deviceConfirmOpen: boolean;
  deviceToDisconnect: DeviceRecord | null;
  deviceDisconnectBusy: boolean;
};
export type DevicesStore = DevicesState & {
  loadDevices(devicesEnabled: boolean, force?: boolean): Promise<void>;
  openDeviceDisconnectDialog(device: DeviceRecord): void;
  closeDeviceDisconnectDialog(): void;
  disconnectDevice(devicesEnabled: boolean): Promise<void>;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function stringField(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function createDevicesStore({
  api,
  t,
  showToast,
}: {
  api: ApiClient["api"];
  t: Translate;
  showToast: (message: string) => void;
}) {
  const store = $state<DevicesStore>({
    devicesData: null,
    devicesLoaded: false,
    devicesBusy: false,
    devicesStatus: "",
    devicesIsError: false,
    devicesErrorCode: "",
    deviceConfirmOpen: false,
    deviceToDisconnect: null,
    deviceDisconnectBusy: false,
    async loadDevices(devicesEnabled: boolean, force = false) {
      if (!devicesEnabled || store.devicesBusy || (store.devicesLoaded && !force)) return;
      store.devicesBusy = true;
      store.devicesStatus = "";
      store.devicesIsError = false;
      store.devicesErrorCode = "";
      try {
        const response = await api("/devices");
        if (!response?.ok) throw response;
        const payload = unwrap(response);
        store.devicesData = payload;
        store.devicesLoaded = true;
        store.devicesErrorCode = "";
      } catch (error: unknown) {
        const errorRecord = asRecord(error);
        store.devicesStatus = stringField(errorRecord.message) || t("wa_devices_load_failed");
        store.devicesIsError = true;
        store.devicesErrorCode = String(errorRecord.error || "");
        store.devicesLoaded = true;
      } finally {
        store.devicesBusy = false;
      }
    },
    openDeviceDisconnectDialog(device: DeviceRecord) {
      store.deviceToDisconnect = device;
      store.deviceConfirmOpen = true;
    },
    closeDeviceDisconnectDialog() {
      if (store.deviceDisconnectBusy) return;
      store.deviceConfirmOpen = false;
      store.deviceToDisconnect = null;
    },
    async disconnectDevice(devicesEnabled: boolean) {
      const token = String(store.deviceToDisconnect?.token || "").trim();
      if (!token || store.deviceDisconnectBusy) return;
      store.deviceDisconnectBusy = true;
      try {
        const response = await api("/devices/disconnect", {
          method: "POST",
          body: JSON.stringify({ token } satisfies PostPayload<"/api/devices/disconnect">),
        });
        if (!response?.ok) throw response;
        unwrap(response);
        showToast(t("wa_device_disconnected"));
        store.deviceConfirmOpen = false;
        store.deviceToDisconnect = null;
        store.devicesLoaded = false;
        await store.loadDevices(devicesEnabled, true);
      } catch (error: unknown) {
        showToast(stringField(asRecord(error).message) || t("wa_device_disconnect_failed"));
      } finally {
        store.deviceDisconnectBusy = false;
      }
    },
  });

  return store;
}
