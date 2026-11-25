<script lang="ts">
  import { onMount, tick } from "svelte";
  import { getRoleApi, getUsersStore } from "$lib/admin/context";
  import { adminErrorMessage } from "$lib/admin/errors";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { Clock, Key, Merge, Trash2, UserMinus, UserPlus } from "$components/ui/icons.js";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState";
  import type { TranslateFn, DateFormatter } from "./userDetailTypes";
  import UserMergeDialog from "./UserMergeDialog.svelte";

  let {
    at,
    openedUser = null,
    openedUserDetail = null,
    fmtDate,
    openedUserIsBanned = false,
    userActionBusy = false,
  }: {
    at: TranslateFn;
    openedUser?: AdminUser | null;
    openedUserDetail?: AdminUserDetail | null;
    fmtDate: DateFormatter;
    openedUserIsBanned?: boolean;
    userActionBusy?: boolean;
  } = $props();

  const usersStore = getUsersStore();
  const roleApi = getRoleApi();
  let rolesAvailable = $state(false);
  let roleAssignments = $state<Array<{ user_id: number; role: string }>>([]);
  let roleBusy = $state(false);
  let roleError = $state("");
  let mergeOpen = $state(false);
  let mergeTrigger: HTMLButtonElement | null = null;
  const subscription = $derived(
    openedUserDetail?.suspended_subscription ?? openedUserDetail?.active_subscription
  );
  const pendingSuspension = $derived(Boolean(subscription?.suspended_at && subscription.is_active));
  const canResume = $derived(Boolean(subscription?.suspended_at && !subscription.is_active));
  const suspensionLabel = $derived(
    canResume
      ? "user_resume_subscription"
      : pendingSuspension
        ? "user_retry_subscription_suspension"
        : "user_suspend_subscription"
  );
  let confirmation = $state<{ userId: number | string; id: number; suspended: boolean } | null>(
    null
  );
  let suspensionError = $state("");
  let suspensionTrigger: HTMLButtonElement | null = null;
  const targetId = $derived(Number(openedUser?.user_id || 0));

  function requestSuspension(event: MouseEvent) {
    if (!openedUser || !subscription || openedUserIsBanned || userActionBusy) return;
    suspensionTrigger =
      event.currentTarget instanceof HTMLButtonElement ? event.currentTarget : null;
    suspensionError = "";
    confirmation = {
      userId: openedUser.user_id,
      id: subscription.subscription_id,
      suspended: !canResume,
    };
  }

  async function closeSuspension() {
    confirmation = null;
    await tick();
    suspensionTrigger?.focus();
  }

  async function confirmSuspension() {
    if (!confirmation || userActionBusy) return;
    suspensionError = "";
    const { userId, id, suspended } = confirmation;
    try {
      if (await usersStore.setSubscriptionSuspension(userId, id, suspended))
        await closeSuspension();
    } catch (cause) {
      suspensionError = adminErrorMessage(cause, at, at("user_subscription_suspension_failed"));
    }
  }

  function closeMerge() {
    mergeOpen = false;
    const trigger = mergeTrigger;
    void tick().then(() => trigger?.isConnected && trigger.focus());
  }
  const targetIsOwner = $derived(
    roleAssignments.some((item) => item.user_id === targetId && item.role === "owner")
  );
  const targetIsAdmin = $derived(
    roleAssignments.some((item) => item.user_id === targetId && item.role === "admin")
  );

  async function loadRoles(): Promise<void> {
    try {
      const response = await roleApi.list();
      rolesAvailable = response !== null;
      if (response) roleAssignments = response;
    } catch (cause) {
      roleError = cause instanceof Error ? cause.message : String(cause);
    }
  }

  onMount(() => {
    void loadRoles();
  });

  async function toggleAdmin(): Promise<void> {
    if (roleBusy || !openedUser?.minishop_id || targetIsOwner) return;
    const message = targetIsAdmin
      ? at("roles_revoke_confirm", {}, "Revoke administrator access for this user?")
      : at("roles_grant_confirm", {}, "Grant administrator access to this user?");
    if (typeof window !== "undefined" && !window.confirm(message)) return;
    roleBusy = true;
    roleError = "";
    try {
      if (targetIsAdmin) await roleApi.revoke(targetId, "admin");
      else await roleApi.grant(openedUser.minishop_id, "admin");
      await loadRoles();
    } catch (cause) {
      roleError = cause instanceof Error ? cause.message : String(cause);
    } finally {
      roleBusy = false;
    }
  }
</script>

<section class="admin-danger-zone">
  <header class="admin-danger-zone-head">
    <strong>{at("user_danger_zone_title", {}, "Danger Zone")}</strong>
    <small>{at("user_danger_zone_subtitle", {}, "Confirm first. Deletion is permanent.")}</small>
    {#if subscription?.suspended_at}
      <small role="status"
        >{at(
          pendingSuspension
            ? "user_subscription_suspension_pending_since"
            : "user_subscription_suspended_since",
          { date: fmtDate(subscription.suspended_at) }
        )}</small
      >
    {/if}
  </header>
  <div class="admin-action-grid">
    <AdminButton
      variant="dangerSoft"
      data-admin-action="request-user-merge"
      disabled={!openedUserDetail || userActionBusy || roleBusy}
      onclick={(event) => {
        mergeTrigger =
          event.currentTarget instanceof HTMLButtonElement ? event.currentTarget : null;
        mergeOpen = true;
      }}><Merge size={14} />{at("user_merge_action")}</AdminButton
    >
    {#if rolesAvailable && openedUser?.minishop_id && !targetIsOwner}
      <AdminButton
        variant="dangerSoft"
        data-admin-action="toggle-user-admin-role"
        onclick={toggleAdmin}
        disabled={userActionBusy || roleBusy}
      >
        {targetIsAdmin
          ? at("roles_demote", {}, "Demote administrator")
          : at("roles_promote", {}, "Make administrator")}
      </AdminButton>
    {/if}
    {#if subscription?.subscription_id}
      <AdminButton
        variant="dangerSoft"
        data-admin-action="request-user-subscription-suspension"
        onclick={requestSuspension}
        disabled={userActionBusy || roleBusy || openedUserIsBanned}
        title={openedUserIsBanned ? at("error_suspension_account_banned") : undefined}
      >
        <Clock size={14} />
        {at(suspensionLabel)}
      </AdminButton>
    {/if}
    {#if openedUserIsBanned}
      <AdminButton
        variant="dangerSoft"
        data-admin-action="request-user-ban-toggle"
        onclick={usersStore.requestBanToggle}
        disabled={userActionBusy}
      >
        <UserPlus size={14} />
        {at("btn_unban", {}, "Unblock user")}
      </AdminButton>
    {:else}
      <AdminButton
        variant="danger"
        data-admin-action="request-user-ban-toggle"
        onclick={usersStore.requestBanToggle}
        disabled={userActionBusy}
      >
        <UserMinus size={14} />
        {at("btn_ban", {}, "Block user")}
      </AdminButton>
    {/if}
    <AdminButton
      variant="dangerSoft"
      data-admin-action="request-user-subscription-reissue"
      onclick={() => usersStore.updateState({ userSubscriptionReissueOpen: true })}
      disabled={userActionBusy}
    >
      <Key size={14} />
      {at("user_btn_reissue_subscription", {}, "Reset subscription link")}
    </AdminButton>
    <AdminButton
      variant="danger"
      data-admin-action="request-user-delete"
      onclick={() => usersStore.updateState({ userDeleteOpen: true })}
      disabled={userActionBusy}
    >
      <Trash2 size={14} />
      {at("btn_delete_account", {}, "Delete account")}
    </AdminButton>
  </div>
  {#if roleError}<p class="admin-error" role="alert">{roleError.replaceAll("_", " ")}</p>{/if}
</section>

{#if confirmation}
  {@const request = confirmation}
  <Dialog
    open
    portal
    title={at(request.suspended ? "user_suspend_subscription" : "user_resume_subscription")}
    description={at(
      request.suspended ? "user_suspend_subscription_details" : "user_resume_subscription_details",
      { id: request.id }
    )}
    closeLabel={at("close", {}, "Close")}
    onclose={() => !userActionBusy && closeSuspension()}
    class="admin-dialog"
  >
    {#if suspensionError}<p class="admin-error" role="alert">{suspensionError}</p>{/if}
    {#snippet footer()}
      <div class="admin-dialog-actions">
        <AdminButton disabled={userActionBusy} onclick={closeSuspension}
          >{at("btn_cancel", {}, "Cancel")}</AdminButton
        >
        <AdminButton
          variant={request.suspended ? "danger" : "primary"}
          disabled={userActionBusy ||
            openedUserIsBanned ||
            request.id !== subscription?.subscription_id ||
            request.suspended === canResume}
          onclick={confirmSuspension}
        >
          {at(request.suspended ? "user_suspend_subscription" : "user_resume_subscription")}
        </AdminButton>
      </div>
    {/snippet}
  </Dialog>
{/if}

{#if openedUserDetail && mergeOpen}
  <UserMergeDialog
    open={mergeOpen}
    target={openedUserDetail}
    {at}
    {fmtDate}
    onclose={closeMerge}
    oncomplete={(source, target) => {
      for (const user of [source, target]) {
        usersStore.invalidateUsersQueries(user.user_id);
        if (user.minishop_id) usersStore.invalidateUsersQueries(user.minishop_id);
      }
      void usersStore.loadUsers({ refresh: true });
    }}
    onmerged={(detail) =>
      usersStore.updateState({ openedUser: detail.user, openedUserDetail: detail })}
  />
{/if}
