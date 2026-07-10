<script lang="ts">
  import { getUsersStore } from "$lib/admin/context";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import { Trash2, UserMinus, UserPlus } from "$components/ui/icons.js";
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
    <strong>{at("user_danger_zone_title", {}, "Опасные действия")}</strong>
    <small
      >{at(
        "user_danger_zone_subtitle",
        {},
        "Эти действия требуют подтверждения и (для удаления) необратимы"
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
        {at("btn_unban", {}, "Разбанить пользователя")}
      </AdminButton>
    {:else}
      <AdminButton
        variant="danger"
        data-admin-action="request-user-ban-toggle"
        onclick={usersStore.requestBanToggle}
        disabled={userActionBusy}
      >
        <UserMinus size={14} />
        {at("btn_ban", {}, "Заблокировать")}
      </AdminButton>
    {/if}
    <AdminButton
      variant="danger"
      data-admin-action="request-user-delete"
      onclick={() => usersStore.updateState({ userDeleteOpen: true })}
      disabled={userActionBusy}
    >
      <Trash2 size={14} />
      {at("btn_delete_account", {}, "Удалить аккаунт")}
    </AdminButton>
  </div>
</section>
