<script lang="ts">
  import { CircleX, Key, Plus, RefreshCw, Smartphone } from "$components/ui/icons.js";

  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import { EmptyCard, LinearProgress, StatusMessage } from "$components/patterns/webapp/index.js";
  import {
    devicesCountLabel,
    devicesLimitLabel,
    devicesPercent,
  } from "../../lib/webapp/devicesLabels.js";
  import type {
    DeviceView,
    DevicesData,
    SubscriptionView,
    Translate,
    VoidAction,
  } from "$lib/webapp/types.js";

  type Props = {
    devicesBusy?: boolean;
    devicesData?: DevicesData;
    devicesErrorCode?: string;
    devicesIsError?: boolean;
    devicesLoaded?: boolean;
    devicesStatus?: string;
    subscription?: SubscriptionView;
    loadDevices?: (force?: boolean) => void;
    openDeviceDisconnectDialog?: (device: DeviceView) => void;
    openDeviceTopupModal?: VoidAction;
    openSubscriptionReissueDialog?: VoidAction;
    subscriptionReissueBusy?: boolean;
    subscriptionReissueEnabled?: boolean;
    t?: Translate;
  };

  let {
    devicesBusy = false,
    devicesData = {},
    devicesErrorCode = "",
    devicesIsError = false,
    devicesLoaded = false,
    devicesStatus = "",
    subscription = {},
    loadDevices = () => {},
    openDeviceDisconnectDialog = () => {},
    openDeviceTopupModal = () => {},
    openSubscriptionReissueDialog = () => {},
    subscriptionReissueBusy = false,
    subscriptionReissueEnabled = false,
    t = (key: string) => key,
  }: Props = $props();

  const deviceList = $derived(Array.isArray(devicesData?.devices) ? devicesData.devices : []);
  const hasDevices = $derived(deviceList.length > 0);
  const subscriptionNotActiveError = $derived(
    devicesErrorCode === "subscription_not_active" || devicesStatus === "Subscription is not active"
  );
  const hideDevicesSummary = $derived(!subscription?.active && !hasDevices);
  const showInactiveDevicesNotice = $derived(
    hideDevicesSummary &&
      !(devicesBusy && !devicesLoaded) &&
      (!devicesStatus || subscriptionNotActiveError)
  );
  const effectiveMaxDevices = $derived(devicesData?.max_devices ?? subscription?.max_devices);
</script>

<main class="content with-nav">
  {#if !hideDevicesSummary}
    <Card class="devices-summary-card">
      <div class="devices-summary-head">
        <Smartphone size={28} />
        <span>
          <strong>{t("wa_devices_title")}</strong>
          <small>{devicesCountLabel(devicesData, t, effectiveMaxDevices)}</small>
        </span>
        <Button
          variant="icon"
          size="icon"
          onclick={() => loadDevices(true)}
          disabled={devicesBusy}
          aria-label={t("wa_devices_refresh")}
        >
          <RefreshCw size={18} />
        </Button>
      </div>
      <LinearProgress
        class="devices-progress"
        value={devicesPercent(devicesData, effectiveMaxDevices)}
        label={t("wa_devices_title")}
      />
      {#if Number(subscription?.extra_hwid_devices || 0) > 0 && subscription?.extra_hwid_devices_valid_until_text}
        <p class="devices-topup-validity">
          {t("wa_hwid_devices_valid_until", {
            count: Number(subscription.extra_hwid_devices || 0),
            date: subscription.extra_hwid_devices_valid_until_text,
          })}
        </p>
      {/if}
      {#if subscription?.active && subscription?.max_devices !== 0 && subscription?.can_topup_devices}
        <Button
          data-webapp-action="open-device-topup"
          variant="secondary"
          class="wide"
          onclick={openDeviceTopupModal}
        >
          <Plus size={17} />
          {t("wa_buy_hwid_devices")}
        </Button>
      {/if}
      {#if subscriptionReissueEnabled && subscription?.active}
        <Button
          data-webapp-action="open-subscription-reissue"
          variant="outline"
          class="wide subscription-reissue-button"
          onclick={openSubscriptionReissueDialog}
          disabled={subscriptionReissueBusy}
        >
          <Key size={17} />
          {t("wa_subscription_reissue_action")}
        </Button>
      {/if}
    </Card>
  {/if}

  {#if devicesBusy && !devicesLoaded}
    <EmptyCard>{t("wa_devices_loading")}</EmptyCard>
  {:else if showInactiveDevicesNotice}
    <EmptyCard class="devices-empty-card devices-inactive-card">
      <CircleX size={28} />
      <span>{t("wa_home_subscription_inactive")}</span>
    </EmptyCard>
  {:else if devicesStatus}
    <EmptyCard>
      <StatusMessage error={devicesIsError}>{devicesStatus}</StatusMessage>
    </EmptyCard>
  {:else if !hasDevices}
    <EmptyCard class="devices-empty-card">
      <Smartphone size={28} />
      <span>{t("wa_devices_empty")}</span>
      <small>
        {t("wa_devices_empty_hint", {
          max: devicesLimitLabel(devicesData, t, effectiveMaxDevices),
        })}
      </small>
    </EmptyCard>
  {:else}
    <div class="devices-list">
      {#each deviceList as device (device.token || device.index)}
        <Card class="device-card">
          <div class="device-card-head">
            <div class="device-icon"><Smartphone size={20} /></div>
            <span>
              <strong
                >{device.display_name ||
                  t("wa_device_fallback_name", { index: device.index })}</strong
              >
              <small>{device.platform_label || t("wa_devices_platform_unknown")}</small>
            </span>
          </div>
          <div class="device-meta">
            {#if device.created_at_text}
              <div>
                <span>{t("wa_devices_connected_at")}</span>
                <strong>{device.created_at_text}</strong>
              </div>
            {/if}
            {#if device.hwid_short}
              <div>
                <span>HWID</span>
                <code>{device.hwid_short}</code>
              </div>
            {/if}
            {#if device.user_agent}
              <div class="device-user-agent">
                <span>User Agent</span>
                <small>{device.user_agent}</small>
              </div>
            {/if}
          </div>
          {#if device.can_disconnect}
            <Button
              data-webapp-action="open-device-disconnect"
              variant="outline"
              class="wide device-disconnect-button"
              onclick={() => openDeviceDisconnectDialog(device)}
            >
              <CircleX size={17} />
              {t("wa_devices_disconnect")}
            </Button>
          {/if}
        </Card>
      {/each}
    </div>
  {/if}
</main>
