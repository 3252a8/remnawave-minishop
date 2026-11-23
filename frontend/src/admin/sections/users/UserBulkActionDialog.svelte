<script lang="ts">
  import { onMount } from "svelte";
  import { getUsersStore } from "$lib/admin/context";
  import { adminErrorMessage } from "$lib/admin/errors";
  import { tariffOptionName } from "$lib/admin/subscriptionPlans";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import {
    bulkUserActionLabels,
    type BulkUserAction,
    type BulkUserActionResult,
  } from "$lib/admin/stores/usersStoreBulkActions";
  import { AdminButton, AdminField, AdminSelect } from "$components/patterns/admin/index.js";
  import type { TranslateFn } from "$components/patterns/admin/types";
  import { Input } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";

  let {
    at,
    currentLang,
    type,
    users,
    userDisplayName,
    onclose,
  }: {
    at: TranslateFn;
    currentLang: string;
    type: BulkUserAction["type"];
    users: readonly AdminUser[];
    userDisplayName: (user: AdminUser) => string;
    onclose: (results: readonly BulkUserActionResult[]) => void;
  } = $props();

  const store = getUsersStore();
  let gb = $state<string | number>("");
  let days = $state<string | number>("");
  let deleteConfirmation = $state<string | number>("");
  let kind = $state<"regular" | "premium">("regular");
  let tariffKey = $state("");
  let tariffs = $state.raw<Awaited<ReturnType<typeof store.loadBulkTariffs>>>([]);
  let tariffLoading = $state(false);
  let tariffError = $state("");
  let busy = $state(false);
  let results = $state.raw<BulkUserActionResult[]>([]);
  const completed = $derived(results.length > 0 && !busy);
  const applied = $derived(results.filter((result) => result.status === "applied").length);
  const rejected = $derived(results.filter((result) => result.status === "rejected").length);
  const unconfirmed = $derived(results.length - applied - rejected);
  const tariffItems = $derived(
    tariffs.map((tariff) => {
      const name = tariffOptionName(
        { tariff_key: tariff.key, tariff_names: tariff.names ?? {} },
        currentLang
      );
      return {
        value: tariff.key,
        label: tariff.enabled === false ? `${name} (${at("user_tariff_hidden_badge")})` : name,
      };
    })
  );
  const trafficItems = $derived([
    { value: "regular", label: at("user_traffic_grant_kind_regular") },
    { value: "premium", label: at("user_traffic_grant_kind_premium") },
  ]);
  const amount = $derived(Number(gb));
  const validGb = $derived(amount <= 1_000_000 && Math.round(amount * 1024 ** 3) > 0);
  const duration = $derived(Number(days));
  const deleteWord = $derived(at("users_bulk_delete_word"));
  const canSubmit = $derived.by(() => {
    switch (type) {
      case "tariff":
        return tariffItems.some((item) => item.value === tariffKey);
      case "traffic-grant":
        return validGb;
      case "extend":
        return Number.isSafeInteger(duration) && duration > 0;
      case "delete":
        return String(deleteConfirmation).trim().toLocaleUpperCase() === deleteWord;
      default:
        return true;
    }
  });
  const userById = $derived(new Map(users.map((user) => [user.user_id, user])));
  const title = $derived(at(bulkUserActionLabels[type]));

  async function loadTariffs() {
    tariffLoading = true;
    tariffError = "";
    try {
      tariffs = await store.loadBulkTariffs();
    } catch (error) {
      tariffError = adminErrorMessage(error, at, at("load_failed"));
    } finally {
      tariffLoading = false;
    }
  }

  onMount(() => {
    if (type === "tariff") void loadTariffs();
  });

  function close() {
    if (!busy) onclose(results);
  }

  function preventUnload(event: BeforeUnloadEvent) {
    if (busy) event.preventDefault();
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!canSubmit || busy || completed || !users.length) return;
    let action: BulkUserAction;
    switch (type) {
      case "tariff":
        action = { type, tariffKey };
        break;
      case "traffic-grant":
        action = { type, kind, gb: amount };
        break;
      case "extend":
        action = { type, days: duration };
        break;
      default:
        action = { type };
    }
    busy = true;
    try {
      await store.applyBulkAction(
        action,
        users.map((user) => user.user_id),
        (result) => {
          results = [...results, result];
        }
      );
    } finally {
      busy = false;
    }
  }
</script>

<svelte:window onbeforeunload={preventUnload} />

<Dialog
  open
  portal
  class="admin-users-bulk-dialog"
  {title}
  description={at("users_bulk_selected", { count: users.length })}
  closeLabel={at("close")}
  showCloseButton={!busy}
  focusKey={completed ? "result" : "form"}
  onclose={close}
>
  {#if completed}
    <div class="bulk-result" data-users-bulk-result>
      <p role="status">{at("users_bulk_applied", { count: applied })}</p>
      {#if rejected}
        <p>{at("users_bulk_rejected", { count: rejected })}</p>
      {/if}
      {#if unconfirmed}
        <p>{at("users_bulk_unconfirmed", { count: unconfirmed })}</p>
      {/if}
      {#if rejected || unconfirmed}
        <ul class="bulk-failures">
          {#each results as result (result.userId)}
            {@const user = userById.get(result.userId)}
            {#if result.status !== "applied" && user}
              <li>
                <strong>{userDisplayName(user)}</strong>
                <small>{user.minishop_id || user.user_id}</small>
                <span>
                  {result.status === "rejected"
                    ? adminErrorMessage(result.error, at)
                    : at("users_bulk_check_user")}
                </span>
              </li>
            {/if}
          {/each}
        </ul>
      {/if}
    </div>
  {:else}
    <form id="admin-users-bulk-form" class="bulk-form" onsubmit={submit}>
      {#if type === "tariff"}
        <p>{at("users_bulk_tariff_hint")}</p>
        {#if tariffLoading}
          <p role="status">{at("loading")}</p>
        {:else if tariffError}
          <p role="alert">{tariffError}</p>
          <AdminButton onclick={loadTariffs}>{at("users_bulk_reload_tariffs")}</AdminButton>
        {:else if !tariffItems.length}
          <p>{at("users_bulk_no_tariffs")}</p>
        {:else}
          <AdminField label={at("user_tariff_select_label")}>
            <AdminSelect
              items={tariffItems}
              value={tariffKey}
              placeholder={at("user_tariff_select_placeholder")}
              ariaLabel={at("user_tariff_select_label")}
              disabled={busy}
              onValueChange={(value) => (tariffKey = value)}
            />
          </AdminField>
        {/if}
      {:else if type === "traffic-grant"}
        <p>{at("users_bulk_traffic_hint")}</p>
        <AdminField label={at("user_traffic_grant_kind")}>
          <AdminSelect
            items={trafficItems}
            value={kind}
            ariaLabel={at("user_traffic_grant_kind")}
            disabled={busy}
            onValueChange={(value) => (kind = value === "premium" ? "premium" : "regular")}
          />
        </AdminField>
        <AdminField label={at("user_traffic_grant_gb")}>
          <Input
            type="number"
            min="0"
            max="1000000"
            step="any"
            placeholder="0"
            disabled={busy}
            aria-label={at("user_traffic_grant_gb")}
            bind:value={gb}
          />
        </AdminField>
      {:else if type === "extend"}
        <p>{at("users_bulk_extend_hint")}</p>
        <AdminField label={at("users_bulk_extend_days")}>
          <Input
            type="number"
            min="1"
            step="1"
            disabled={busy}
            aria-label={at("users_bulk_extend_days")}
            bind:value={days}
          />
        </AdminField>
      {:else if type === "traffic-reset"}
        <p>{at("users_bulk_reset_hint")}</p>
      {:else if type === "subscription-reissue"}
        <p>{at("user_subscription_reissue_confirm_subtitle")}</p>
      {:else}
        <p>{at("users_bulk_delete_hint")}</p>
        <ul class="bulk-targets">
          {#each users as user (user.user_id)}
            <li>
              <strong>{userDisplayName(user)}</strong>
              <small>{user.minishop_id || user.user_id}</small>
            </li>
          {/each}
        </ul>
        <AdminField label={at("users_bulk_delete_confirmation", { word: deleteWord })}>
          <Input
            autocomplete="off"
            spellcheck={false}
            disabled={busy}
            aria-label={at("users_bulk_delete_confirmation", { word: deleteWord })}
            bind:value={deleteConfirmation}
          />
        </AdminField>
      {/if}
      {#if busy}
        <p role="status"
          >{at("users_bulk_progress", { done: results.length, total: users.length })}</p
        >
      {/if}
    </form>
  {/if}
  {#snippet footer()}
    <div class="bulk-dialog-actions">
      <AdminButton onclick={close} disabled={busy}>
        {completed ? at("close") : at("cancel")}
      </AdminButton>
      {#if !completed}
        <AdminButton
          type="submit"
          form="admin-users-bulk-form"
          variant={type === "delete" ? "danger" : "primary"}
          disabled={!canSubmit || busy}
        >
          {type === "delete" ? at("users_bulk_delete_submit", { count: users.length }) : title}
        </AdminButton>
      {/if}
    </div>
  {/snippet}
</Dialog>

<style>
  :global(.admin-users-bulk-dialog) {
    width: min(100%, 440px);
  }

  .bulk-form,
  .bulk-result,
  .bulk-failures {
    display: grid;
    gap: 12px;
    min-width: 0;
  }

  p,
  .bulk-failures {
    margin: 0;
  }

  .bulk-targets {
    display: grid;
    gap: 8px;
    margin: 0;
    padding-inline-start: 20px;
    overflow-wrap: anywhere;
  }

  .bulk-targets small {
    display: block;
    color: var(--admin-muted);
  }

  .bulk-form p,
  .bulk-failures small {
    color: var(--admin-muted);
  }

  .bulk-failures {
    padding: 0;
    list-style: none;
  }

  .bulk-failures li {
    display: grid;
    gap: 4px;
    padding-block-start: 10px;
    border-top: 1px solid var(--admin-border);
    overflow-wrap: anywhere;
  }

  .bulk-dialog-actions {
    display: flex;
    justify-content: flex-end;
    flex-wrap: wrap;
    gap: 8px;
  }
</style>
