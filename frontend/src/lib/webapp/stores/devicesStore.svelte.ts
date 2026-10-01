import type { ApiClient, DevicesResponse, PostPayload } from "../publicApi";
import {
  buildDevicesDisconnectPath,
  buildDevicesPath,
  buildDevicesRenamePath,
  unwrap,
} from "../publicApi";
import type { DeviceView } from "../types";
import { DEVICE_NAME_MAX_LENGTH, normalizeDeviceName } from "../deviceNames";

export { DEVICE_NAME_MAX_LENGTH } from "../deviceNames";

type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
export type DevicesState = {
  devicesData: DevicesResponse | null;
  devicesLoaded: boolean;
  devicesBusy: boolean;
  devicesStatus: string;
  devicesIsError: boolean;
  devicesErrorCode: string;
  deviceConfirmOpen: boolean;
  deviceToDisconnect: DeviceView | null;
  deviceDisconnectBusy: boolean;
  deviceRenameOpen: boolean;
  deviceToRename: DeviceView | null;
  deviceRenameValue: string;
  deviceRenameBusy: boolean;
  deviceRenameError: string;
};
export type DevicesStore = DevicesState & {
  loadDevices(devicesEnabled: boolean, force?: boolean): Promise<void>;
  openDeviceDisconnectDialog(device: DeviceView): void;
  closeDeviceDisconnectDialog(): void;
  disconnectDevice(devicesEnabled: boolean): Promise<void>;
  openDeviceRenameDialog(device: DeviceView): void;
  closeDeviceRenameDialog(): void;
  renameDevice(name?: string): Promise<void>;
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
    deviceRenameOpen: false,
    deviceToRename: null,
    deviceRenameValue: "",
    deviceRenameBusy: false,
    deviceRenameError: "",
    async loadDevices(devicesEnabled: boolean, force = false) {
      if (!devicesEnabled || store.devicesBusy || (store.devicesLoaded && !force)) return;
      store.devicesBusy = true;
      store.devicesStatus = "";
      store.devicesIsError = false;
      store.devicesErrorCode = "";
      try {
        const response = await api(buildDevicesPath());
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
    openDeviceDisconnectDialog(device: DeviceView) {
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
        const response = await api(buildDevicesDisconnectPath(), {
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
    openDeviceRenameDialog(device: DeviceView) {
      store.deviceToRename = device;
      store.deviceRenameValue = String(device.custom_name || "");
      store.deviceRenameError = "";
      store.deviceRenameOpen = true;
    },
    closeDeviceRenameDialog() {
      if (store.deviceRenameBusy) return;
      store.deviceRenameOpen = false;
      store.deviceToRename = null;
      store.deviceRenameError = "";
    },
    async renameDevice(name?: string) {
      const token = String(store.deviceToRename?.token || "").trim();
      if (!token || store.deviceRenameBusy) return;
      const value = normalizeDeviceName(name ?? store.deviceRenameValue);
      if (Array.from(value).length > DEVICE_NAME_MAX_LENGTH) {
        store.deviceRenameError = t("wa_device_name_too_long", { max: DEVICE_NAME_MAX_LENGTH });
        return;
      }
      store.deviceRenameBusy = true;
      store.deviceRenameError = "";
      try {
        const response = await api(buildDevicesRenamePath(), {
          method: "POST",
          body: JSON.stringify({
            token,
            name: value,
          } satisfies PostPayload<"/api/devices/rename">),
        });
        if (!response?.ok) throw response;
        const updated = unwrap(response).device;
        const devices = store.devicesData?.devices;
        if (store.devicesData && Array.isArray(devices)) {
          store.devicesData = {
            ...store.devicesData,
            devices: devices.map((device) => (device.token === token ? updated : device)),
          };
        }
        showToast(value ? t("wa_device_renamed") : t("wa_device_name_restored"));
        store.deviceRenameOpen = false;
        store.deviceToRename = null;
      } catch (error: unknown) {
        store.deviceRenameError =
          String(asRecord(error).error || "") === "device_name_too_long"
            ? t("wa_device_name_too_long", { max: DEVICE_NAME_MAX_LENGTH })
            : t("wa_device_rename_failed");
      } finally {
        store.deviceRenameBusy = false;
      }
    },
  });

  return store;
}
