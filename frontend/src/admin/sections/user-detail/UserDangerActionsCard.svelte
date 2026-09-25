<script lang="ts">
  import { onMount } from "svelte";
  import { getRoleApi, getUsersStore } from "$lib/admin/context";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import { Key, Trash2, UserMinus, UserPlus } from "$components/ui/icons.js";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import type { TranslateFn } from "./userDetailTypes";

  let {
    at,
    openedUser = null,
    openedUserIsBanned = false,
    userActionBusy = false,
  }: {
    at: TranslateFn;
    openedUser?: AdminUser | null;
    openedUserIsBanned?: boolean;
    userActionBusy?: boolean;
  } = $props();

  const usersStore = getUsersStore();
  const roleApi = getRoleApi();
  let rolesAvailable = $state(false);
  let roleAssignments = $state<Array<{ user_id: number; role: string }>>([]);
  let roleBusy = $state(false);
  let roleError = $state("");
  const targetId = $derived(Number(openedUser?.user_id || 0));
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
    <small
      >{at(
        "user_danger_zone_subtitle",
        {},
        "These actions require confirmation and (for deletion) are irreversible"
      )}</small
    >
  </header>
  <div class="admin-action-grid">
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
