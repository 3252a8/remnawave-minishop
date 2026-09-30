<script lang="ts">
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import Input from "$components/ui/input.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";
  import { DEVICE_NAME_MAX_LENGTH } from "$lib/webapp/stores/devicesStore.js";
  import type { DeviceView, Translate, VoidAction } from "$lib/webapp/types.js";

  let {
    open = false,
    busy = false,
    device = null,
    value = $bindable(""),
    error = "",
    onsave = () => {},
    onreset = () => {},
    onclose = () => {},
    t = (key) => key,
  }: {
    open?: boolean;
    busy?: boolean;
    device?: DeviceView | null;
    value?: string;
    error?: string;
    onsave?: VoidAction;
    onreset?: VoidAction;
    onclose?: VoidAction;
    t?: Translate;
  } = $props();

  const defaultName = $derived(String(device?.default_name || device?.display_name || ""));
</script>

<Dialog
  {open}
  title={t("wa_devices_rename_title")}
  description={t("wa_devices_rename_desc", { max: DEVICE_NAME_MAX_LENGTH })}
  closeLabel={t("wa_close")}
  {onclose}
  class="payment-dialog-card webapp-device-rename-dialog"
>
  <form
    class="payment-dialog-body"
    onsubmit={(event) => {
      event.preventDefault();
      onsave();
    }}
  >
    <Input
      bind:value
      name="device-name"
      autocomplete="off"
      placeholder={defaultName}
      disabled={busy}
      aria-label={t("wa_devices_rename_title")}
    />
    {#if error}
      <StatusMessage error>{error}</StatusMessage>
    {/if}
    <Button data-webapp-action="save-device-name" class="wide" type="submit" disabled={busy}>
      {t("wa_devices_rename_save")}
    </Button>
    {#if device?.custom_name}
      <Button variant="secondary" class="wide" onclick={onreset} disabled={busy}>
        {t("wa_devices_rename_reset")}
      </Button>
    {/if}
  </form>
</Dialog>
