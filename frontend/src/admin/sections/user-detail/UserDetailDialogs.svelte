<script lang="ts">
  import { getUsersStore } from "$lib/admin/context";
  import { ScrollArea } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminButton,
    AdminEmptyState,
    AdminPagination,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
  import { ExternalLink, Send, Trash2, UserMinus } from "$components/ui/icons.js";
  import type { AdminUser } from "$lib/admin/stores/usersStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type DateFormatter = (value: unknown) => string;
  type Props = {
    at: TranslateFn;
    fmtDateShort?: DateFormatter;
    userDisplayName: (user: AdminUser) => string;
    userSecondaryName: (user: AdminUser) => string;
    openRelatedUser: (user: AdminUser) => void;
    closeAvatarPreview: () => void;
    openedUser?: AdminUser | null;
    userReferralsOpen?: boolean;
    userReferralsLoading?: boolean;
    userReferralsRows?: readonly AdminUser[];
    userReferralsTotal?: number;
    userReferralsPage?: number;
    userReferralsPageCount?: number;
    userReferralsPageSize?: number;
    avatarPreviewOpen?: boolean;
    avatarPreviewUrl?: string;
    avatarPreviewName?: string;
    userMessageConfirmOpen?: boolean;
    userMessageDraft?: string;
    userBanConfirmOpen?: boolean;
    userDeleteOpen?: boolean;
    userActionBusy?: boolean;
  };

  let {
    at,
    fmtDateShort = (value) => String(value ?? ""),
    userDisplayName,
    userSecondaryName,
    openRelatedUser,
    closeAvatarPreview,
    openedUser = null,
    userReferralsOpen = false,
    userReferralsLoading = false,
    userReferralsRows = [],
    userReferralsTotal = 0,
    userReferralsPage = 0,
    userReferralsPageCount = 1,
    userReferralsPageSize = 25,
    avatarPreviewOpen = false,
    avatarPreviewUrl = "",
    avatarPreviewName = "",
    userMessageConfirmOpen = false,
    userMessageDraft = "",
    userBanConfirmOpen = false,
    userDeleteOpen = false,
    userActionBusy = false,
  }: Props = $props();

  const usersStore = getUsersStore();
</script>

<Dialog
  open={userReferralsOpen}
  title={at("user_invitees_title", {}, "Приглашённые пользователи")}
  description={openedUser
    ? at(
        "user_invitees_description",
        { name: userDisplayName(openedUser), count: userReferralsTotal },
        `${userDisplayName(openedUser)} · ${userReferralsTotal}`
      )
    : ""}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={usersStore.closeUserReferrals}
  class="admin-dialog admin-user-referrals-dialog"
>
  <div class="admin-user-referrals-body">
    {#if userReferralsLoading}
      <AdminTableSkeleton
        headers={[
          at("user_col_user", {}, "Пользователь"),
          "ID",
          at("user_label_registration", {}, "Регистрация"),
          "",
        ]}
        rows={5}
        widths={["42%", "18%", "26%", "14%"]}
      />
    {:else if !userReferralsRows.length}
      <AdminEmptyState tone="card">
        <span class="admin-muted"
          >{at("user_invitees_empty", {}, "Пользователь пока никого не пригласил")}</span
        >
      </AdminEmptyState>
    {:else}
      <ScrollArea class="admin-user-referrals-table-wrap" maxHeight="min(55vh, 460px)">
        <AdminTable class="admin-user-referrals-table">
          <thead>
            <tr>
              <th>{at("user_col_user", {}, "Пользователь")}</th>
              <th>ID</th>
              <th>{at("user_label_registration", {}, "Регистрация")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each userReferralsRows as invitee (invitee.user_id)}
              <tr>
                <td data-label={at("user_col_user", {}, "Пользователь")}>
                  <span class="admin-referral-user-cell">
                    <strong>{userDisplayName(invitee)}</strong>
                    <small>{userSecondaryName(invitee)}</small>
                  </span>
                </td>
                <td class="admin-cell-mono" data-label="ID">{invitee.user_id}</td>
                <td data-label={at("user_label_registration", {}, "Регистрация")}>
                  {fmtDateShort(invitee.registration_date)}
                </td>
                <td class="admin-referral-user-actions">
                  <AdminButton
                    size="icon"
                    variant="icon"
                    title={at("user_open_related", {}, "Открыть карточку")}
                    aria-label={at("user_open_related", {}, "Открыть карточку")}
                    onclick={() => openRelatedUser(invitee)}
                  >
                    <ExternalLink size={14} />
                  </AdminButton>
                </td>
              </tr>
            {/each}
          </tbody>
        </AdminTable>
      </ScrollArea>
    {/if}

    {#if userReferralsTotal > userReferralsPageSize}
      <AdminPagination
        page={userReferralsPage}
        pageCount={userReferralsPageCount}
        total={userReferralsTotal}
        pageLabel={at("page_short", {}, "Стр.")}
        ofLabel={at("pagination_of", {}, "из")}
        totalLabel={at("total", {}, "Всего")}
        jumpLabel={at("page_short", {}, "Стр.")}
        jumpAriaLabel={at("pagination_jump_aria", {}, "Перейти к странице")}
        goLabel={at("pagination_go", {}, "Перейти")}
        prevLabel={at("prev_page", {}, "Назад")}
        nextLabel={at("next_page", {}, "Вперёд")}
        disabled={userReferralsLoading}
        onPageChange={(page) => usersStore.setUserReferralsPage(page)}
      />
    {/if}
  </div>
</Dialog>

<Dialog
  open={avatarPreviewOpen}
  title={avatarPreviewName || at("user_avatar_title", {}, "Аватар")}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={closeAvatarPreview}
  class="admin-dialog admin-avatar-dialog"
>
  {#if avatarPreviewUrl}
    <div class="admin-avatar-preview">
      <img
        src={avatarPreviewUrl}
        alt={avatarPreviewName}
        loading="eager"
        referrerpolicy="no-referrer"
      />
    </div>
  {/if}
</Dialog>

<Dialog
  open={userMessageConfirmOpen}
  title={at("user_msg_confirm_title", {}, "Отправить сообщение пользователю?")}
  description={openedUser
    ? at(
        "user_msg_confirm_recipient",
        { name: userDisplayName(openedUser) },
        `Получатель: ${userDisplayName(openedUser)}`
      )
    : ""}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={() => usersStore.updateState({ userMessageConfirmOpen: false })}
  class="admin-dialog admin-user-message-confirm-dialog"
>
  <ScrollArea class="admin-confirm-message-preview" maxHeight="min(280px, 45vh)">
    {userMessageDraft}
  </ScrollArea>
  <div class="admin-dialog-actions">
    <AdminButton onclick={() => usersStore.updateState({ userMessageConfirmOpen: false })}
      >{at("btn_cancel", {}, "Отмена")}</AdminButton
    >
    <AdminButton
      variant="primary"
      onclick={usersStore.sendUserMessage}
      disabled={userActionBusy || !userMessageDraft.trim()}
    >
      <Send size={14} />
      {at("btn_confirm_send", {}, "Подтвердить отправку")}
    </AdminButton>
  </div>
</Dialog>

<Dialog
  open={userBanConfirmOpen}
  title={at("user_ban_confirm_title", {}, "Заблокировать пользователя?")}
  description={openedUser
    ? at(
        "user_ban_confirm_subtitle",
        { name: userDisplayName(openedUser) },
        `${userDisplayName(openedUser)} больше не сможет взаимодействовать с ботом. Действие можно отменить позже.`
      )
    : ""}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={() => usersStore.updateState({ userBanConfirmOpen: false })}
  class="admin-dialog admin-user-ban-confirm-dialog"
>
  <div class="admin-dialog-actions">
    <AdminButton onclick={() => usersStore.updateState({ userBanConfirmOpen: false })}
      >{at("btn_cancel", {}, "Отмена")}</AdminButton
    >
    <AdminButton
      variant="danger"
      onclick={() => usersStore.applyBanToggle(true)}
      disabled={userActionBusy}
    >
      <UserMinus size={14} />
      {at("btn_ban", {}, "Заблокировать")}
    </AdminButton>
  </div>
</Dialog>

<Dialog
  open={userDeleteOpen}
  title={at("user_delete_confirm_title", {}, "Удалить пользователя?")}
  description={at(
    "user_delete_confirm_subtitle",
    {},
    "Действие необратимо. Удалятся записи в БД бота и пользователь в Remnawave Panel."
  )}
  closeLabel={at("close", {}, "Закрыть")}
  onclose={() => usersStore.updateState({ userDeleteOpen: false })}
  class="admin-dialog admin-user-delete-dialog"
>
  <div class="admin-form-row">
    <AdminButton onclick={() => usersStore.updateState({ userDeleteOpen: false })}
      >{at("btn_cancel", {}, "Отмена")}</AdminButton
    >
    <AdminButton variant="danger" onclick={usersStore.deleteUser} disabled={userActionBusy}>
      <Trash2 size={14} />
      {at("btn_confirm_delete", {}, "Подтвердить удаление")}
    </AdminButton>
  </div>
</Dialog>
