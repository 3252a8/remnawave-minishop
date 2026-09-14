<script lang="ts">
  import { CircleX } from "$components/ui/icons.js";

  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import type { DeviceView, Translate, VoidAction } from "$lib/webapp/types.js";

  type DeviceToDisconnect = DeviceView & {
    display_name?: string | null;
    index?: number | string | null;
  };

  let {
    deviceConfirmOpen = false,
    deviceDisconnectBusy = false,
    deviceToDisconnect = null,
    disconnectDevice = () => {},
    closeDeviceDisconnectDialog = () => {},
    t = (key) => key,
  }: {
    deviceConfirmOpen?: boolean;
    deviceDisconnectBusy?: boolean;
    deviceToDisconnect?: DeviceToDisconnect | null;
    disconnectDevice?: VoidAction;
    closeDeviceDisconnectDialog?: VoidAction;
    t?: Translate;
  } = $props();
</script>

<Dialog
  open={deviceConfirmOpen}
  title={t("wa_devices_disconnect_title")}
  description={t("wa_devices_disconnect_desc", {
    device:
      deviceToDisconnect?.display_name ||
      t("wa_device_fallback_name", { index: deviceToDisconnect?.index || "" }),
  })}
  closeLabel={t("wa_close")}
  onclose={closeDeviceDisconnectDialog}
  class="payment-dialog-card webapp-device-disconnect-dialog"
  showCloseButton={false}
>
  <div class="payment-dialog-body">
    <Button
      variant="outline"
      class="wide device-danger-button"
      onclick={disconnectDevice}
      disabled={deviceDisconnectBusy}
    >
      <CircleX size={17} />
      {t("wa_devices_disconnect_confirm")}
    </Button>
    <Button
      variant="secondary"
      class="wide"
      onclick={closeDeviceDisconnectDialog}
      disabled={deviceDisconnectBusy}
    >
      {t("wa_cancel")}
    </Button>
  </div>
</Dialog>
