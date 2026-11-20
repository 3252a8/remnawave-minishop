<script lang="ts">
  import { onDestroy, onMount, tick } from "svelte";
  import {
    AdminButton,
    AdminEmptyState,
    AdminListToolbar,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { RefreshCw, Trash2 } from "$components/ui/icons.js";
  import { getAdminApi, getUsersStore } from "$lib/admin/context";
  import { adminErrorMessage } from "$lib/admin/errors";
  import type { components } from "$lib/api/openapi.generated";
  import { deviceClientLabel } from "$lib/webapp/deviceClient";
  import {
    buildAdminUserDevicesPath,
    buildAdminUserDisconnectDevicePath,
  } from "$lib/webapp/adminUserPanelPaths";
  import { unwrap } from "$lib/webapp/publicApi";
  import type { DateFormatter, TranslateFn } from "./userDetailTypes";

  type Device = components["schemas"]["WebAppDeviceOut"];
  let {
    at,
    fmtDate,
    userId,
  }: { at: TranslateFn; fmtDate: DateFormatter; userId: number | string } = $props();
  const api = getAdminApi();
  const reads = new AbortController();
  const users = getUsersStore();
  let devices = $state<Device[] | null>(null);
  let selected = $state<Device | null>(null);
  let busy = $state(false);
  let error = $state("");
  let refreshButton: HTMLDivElement;
  let trigger: HTMLButtonElement | null = null;

  function updateCount(count: number) {
    const detail = users.openedUserDetail;
    if (detail?.user.user_id !== userId || !detail.hwid_devices) return;
    users.updateState({
      openedUserDetail: {
        ...detail,
        hwid_devices: { ...detail.hwid_devices, current_devices: count },
      },
    });
  }

  async function load() {
    if (busy) return;
    busy = true;
    error = "";
    try {
      const response = await api(buildAdminUserDevicesPath(userId), { signal: reads.signal });
      if (reads.signal.aborted) return;
      if (!response?.ok) throw response;
      devices = unwrap(response).devices;
      updateCount(devices.length);
    } catch (cause) {
      devices = null;
      error = adminErrorMessage(
        cause,
        at,
        at("user_devices_load_failed", {}, "Could not load the registered devices.")
      );
    } finally {
      busy = false;
    }
  }

  async function close() {
    if (busy) return;
    selected = null;
    await tick();
    if (trigger?.isConnected) trigger.focus();
    else refreshButton?.querySelector("button")?.focus();
  }

  async function disconnect() {
    if (!selected || busy) return;
    const token = selected.token;
    busy = true;
    error = "";
    try {
      const response = await api(buildAdminUserDisconnectDevicePath(userId), {
        method: "POST",
        body: JSON.stringify({ device_token: token }),
      });
      if (!response?.ok) throw response;
      users.invalidateUsersQueries(userId);
      devices = devices?.filter((device) => device.token !== token) ?? null;
      if (devices) updateCount(devices.length);
    } catch (cause) {
      error = adminErrorMessage(
        cause,
        at,
        at(
          "user_device_remove_failed",
          {},
          "Could not remove this device. Refresh the list and try again."
        )
      );
    } finally {
      busy = false;
      await close();
    }
  }

  onMount(() => {
    void load();
  });
  onDestroy(() => reads.abort());
</script>

<AdminListToolbar total={devices?.length} totalLabel={at("total", {}, "Total")}>
  {#snippet actions()}
    <div bind:this={refreshButton}>
      <AdminButton size="sm" disabled={busy} onclick={load}>
        <RefreshCw size={14} />{at("refresh", {}, "Refresh")}
      </AdminButton>
    </div>
  {/snippet}
</AdminListToolbar>
{#if error}<p class="admin-field-error" role="alert">{error}</p>{/if}
{#if devices === null}
  {#if busy}<p class="admin-muted" role="status">{at("loading", {}, "Loading…")}</p>{/if}
{:else if !devices.length}
  <AdminEmptyState title={at("user_devices_empty", {}, "No registered devices")} tone="card" />
{:else}
  <AdminTable class="admin-table-compact" minWidth="680px" layout="fixed">
    <thead>
      <tr>
        <th>{at("user_device", {}, "Device")}</th>
        <th>{at("user_device_platform", {}, "Platform")}</th>
        <th>{at("user_device_client", {}, "Connection app")}</th>
        <th>{at("user_device_last_seen", {}, "Last connection")}</th>
        <th>{at("actions", {}, "Actions")}</th>
      </tr>
    </thead>
    <tbody>
      {#each devices as device (device.index)}
        <tr>
          <td class="admin-cell-wrap" data-label={at("user_device", {}, "Device")}>
            <strong>{device.display_name}</strong>
            {#if device.hwid_short}<div class="admin-muted"><code>{device.hwid_short}</code></div
              >{/if}
          </td>
          <td class="admin-cell-wrap" data-label={at("user_device_platform", {}, "Platform")}>
            {device.platform_label || "—"}
          </td>
          <td class="admin-cell-wrap" data-label={at("user_device_client", {}, "Connection app")}>
            {deviceClientLabel(device.user_agent) ||
              at("user_device_client_unknown", {}, "Not reported")}
          </td>
          <td data-label={at("user_device_last_seen", {}, "Last connection")}>
            {device.last_connected_at ? fmtDate(device.last_connected_at) : "—"}
          </td>
          <td data-label={at("actions", {}, "Actions")}>
            <AdminButton
              size="sm"
              variant="dangerSoft"
              disabled={busy || !device.can_disconnect || !device.token}
              aria-label={at(
                "user_device_remove_named",
                { device: device.display_name },
                "Remove {device}"
              )}
              onclick={(event) => {
                trigger =
                  event.currentTarget instanceof HTMLButtonElement ? event.currentTarget : null;
                selected = device;
              }}><Trash2 size={14} />{at("delete", {}, "Delete")}</AdminButton
            >
          </td>
        </tr>
      {/each}
    </tbody>
  </AdminTable>
{/if}

<Dialog
  open={Boolean(selected)}
  title={at("user_device_remove_title", {}, "Remove this device?")}
  description={at(
    "user_device_remove_hint",
    { device: selected?.display_name || "" },
    "{device} can register again when it reconnects."
  )}
  closeLabel={at("close", {}, "Close")}
  onclose={close}
  portal
  class="admin-dialog"
>
  {#if selected?.hwid_short}<code>{selected.hwid_short}</code>{/if}
  <div class="admin-dialog-actions">
    <AdminButton disabled={busy} onclick={close}>{at("btn_cancel", {}, "Cancel")}</AdminButton>
    <AdminButton disabled={busy} variant="danger" onclick={disconnect}
      >{at("delete", {}, "Delete")}</AdminButton
    >
  </div>
</Dialog>
