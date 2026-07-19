<script lang="ts">
  import { getUsersStore } from "$lib/admin/context";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import { Key, Trash2, UserMinus, UserPlus } from "$components/ui/icons.js";
  import type { TranslateFn } from "./userDetailTypes";

  let {
    at,
    openedUserIsBanned = false,
    userActionBusy = false,
  }: {
    at: TranslateFn;
    openedUserIsBanned?: boolean;
    userActionBusy?: boolean;
  } = $props();

  const usersStore = getUsersStore();
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
</section>
