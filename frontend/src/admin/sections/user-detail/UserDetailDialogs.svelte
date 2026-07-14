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
  import { ExternalLink, RefreshCw, Send, Trash2, UserMinus } from "$components/ui/icons.js";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import type { DateFormatter, TranslateFn } from "./userDetailTypes";

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
    userTariffHwidConfirmOpen?: boolean;
    tariffHwidCurrentLabel?: string;
    tariffHwidTargetLabel?: string;
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
    userTariffHwidConfirmOpen = false,
    tariffHwidCurrentLabel = "",
    tariffHwidTargetLabel = "",
    userDeleteOpen = false,
    userActionBusy = false,
  }: Props = $props();

  const usersStore = getUsersStore();
</script>

<Dialog
  open={userReferralsOpen}
  title={at("user_invitees_title", {}, "Invited users")}
  description={openedUser
    ? at(
        "user_invitees_description",
        { name: userDisplayName(openedUser), count: userReferralsTotal },
        `${userDisplayName(openedUser)} · ${userReferralsTotal}`
      )
    : ""}
  closeLabel={at("close", {}, "Close")}
  onclose={usersStore.closeUserReferrals}
  class="admin-dialog admin-user-referrals-dialog"
>
  <div class="admin-user-referrals-body">
    {#if userReferralsLoading}
      <AdminTableSkeleton
        headers={[
          at("user_col_user", {}, "User"),
          "ID",
          at("user_label_registration", {}, "Registration"),
          "",
        ]}
        rows={5}
        widths={["42%", "18%", "26%", "14%"]}
      />
    {:else if !userReferralsRows.length}
      <AdminEmptyState tone="card">
        <span class="admin-muted"
          >{at("user_invitees_empty", {}, "This user has not invited anyone yet.")}</span
        >
      </AdminEmptyState>
    {:else}
      <ScrollArea class="admin-user-referrals-table-wrap" maxHeight="min(55vh, 460px)">
        <AdminTable class="admin-user-referrals-table">
          <thead>
            <tr>
              <th>{at("user_col_user", {}, "User")}</th>
              <th>ID</th>
              <th>{at("user_label_registration", {}, "Registration")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each userReferralsRows as invitee (invitee.user_id)}
              <tr>
                <td data-label={at("user_col_user", {}, "User")}>
                  <span class="admin-referral-user-cell">
                    <strong>{userDisplayName(invitee)}</strong>
                    <small>{userSecondaryName(invitee)}</small>
                  </span>
                </td>
                <td class="admin-cell-mono" data-label="ID">{invitee.user_id}</td>
                <td data-label={at("user_label_registration", {}, "Registration")}>
                  {fmtDateShort(invitee.registration_date)}
                </td>
                <td class="admin-referral-user-actions">
                  <AdminButton
                    size="icon"
                    variant="icon"
                    title={at("user_open_related", {}, "Open user card")}
                    aria-label={at("user_open_related", {}, "Open user card")}
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
        pageLabel={at("page_short", {}, "Page")}
        ofLabel={at("pagination_of", {}, "of")}
        totalLabel={at("total", {}, "Total")}
        jumpLabel={at("page_short", {}, "Page")}
        jumpAriaLabel={at("pagination_jump_aria", {}, "Go to page")}
        goLabel={at("pagination_go", {}, "Go")}
        prevLabel={at("prev_page", {}, "Back")}
        nextLabel={at("next_page", {}, "Next")}
        disabled={userReferralsLoading}
        onPageChange={(page) => usersStore.setUserReferralsPage(page)}
      />
    {/if}
  </div>
</Dialog>

<Dialog
  open={avatarPreviewOpen}
  title={avatarPreviewName || at("user_avatar_title", {}, "Avatar")}
  closeLabel={at("close", {}, "Close")}
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
  title={at("user_msg_confirm_title", {}, "Send message to user?")}
  description={openedUser
    ? at("user_msg_confirm_recipient", { name: userDisplayName(openedUser) }, "Recipient: {name}")
    : ""}
  closeLabel={at("close", {}, "Close")}
  onclose={() => usersStore.updateState({ userMessageConfirmOpen: false })}
  class="admin-dialog admin-user-message-confirm-dialog"
>
  <ScrollArea class="admin-confirm-message-preview" maxHeight="min(280px, 45vh)">
    {userMessageDraft}
  </ScrollArea>
  <div class="admin-dialog-actions">
    <AdminButton onclick={() => usersStore.updateState({ userMessageConfirmOpen: false })}
      >{at("btn_cancel", {}, "Cancel")}</AdminButton
    >
    <AdminButton
      variant="primary"
      onclick={usersStore.sendUserMessage}
      disabled={userActionBusy || !userMessageDraft.trim()}
    >
      <Send size={14} />
      {at("btn_confirm_send", {}, "Confirm send")}
    </AdminButton>
  </div>
</Dialog>

<Dialog
  open={userBanConfirmOpen}
  title={at("user_ban_confirm_title", {}, "Ban user?")}
  description={openedUser
    ? at(
        "user_ban_confirm_subtitle",
        { name: userDisplayName(openedUser) },
        "{name} will no longer be able to interact with the bot. This can be undone later."
      )
    : ""}
  closeLabel={at("close", {}, "Close")}
  onclose={() => usersStore.updateState({ userBanConfirmOpen: false })}
  class="admin-dialog admin-user-ban-confirm-dialog"
>
  <div class="admin-dialog-actions">
    <AdminButton onclick={() => usersStore.updateState({ userBanConfirmOpen: false })}
      >{at("btn_cancel", {}, "Cancel")}</AdminButton
    >
    <AdminButton
      variant="danger"
      onclick={() => usersStore.applyBanToggle(true)}
      disabled={userActionBusy}
    >
      <UserMinus size={14} />
      {at("btn_ban", {}, "Block user")}
    </AdminButton>
  </div>
</Dialog>

<Dialog
  open={userTariffHwidConfirmOpen}
  title={at("user_tariff_hwid_confirm_title", {}, "Apply the tariff HWID limit?")}
  description={at(
    "user_tariff_hwid_confirm_subtitle",
    {},
    "This user has a manual HWID limit. By default it will be preserved after the tariff change."
  )}
  closeLabel={at("close", {}, "Close")}
  onclose={() =>
    usersStore.updateState({
      userTariffHwidConfirmOpen: false,
      userApplyTariffHwidLimit: false,
    })}
  class="admin-dialog admin-user-tariff-hwid-confirm-dialog"
>
  <div class="admin-tariff-hwid-confirm-summary">
    <span>
      {at("user_tariff_hwid_confirm_before", {}, "Before")}
      <strong>{tariffHwidCurrentLabel || "—"}</strong>
    </span>
    <span>
      {at("user_tariff_hwid_confirm_after", {}, "Tariff limit")}
      <strong>{tariffHwidTargetLabel || "—"}</strong>
    </span>
  </div>
  <div class="admin-dialog-actions">
    <AdminButton
      variant="primary"
      onclick={() => {
        usersStore.updateState({
          userTariffHwidConfirmOpen: false,
          userApplyTariffHwidLimit: false,
        });
        usersStore.changeUserTariff();
      }}
      disabled={userActionBusy}
    >
      <RefreshCw size={14} />
      {at("user_tariff_hwid_confirm_keep", {}, "Keep current limit")}
    </AdminButton>
    <AdminButton
      onclick={() => {
        usersStore.updateState({
          userTariffHwidConfirmOpen: false,
          userApplyTariffHwidLimit: true,
        });
        usersStore.changeUserTariff();
      }}
      disabled={userActionBusy}
    >
      <RefreshCw size={14} />
      {at("user_tariff_hwid_confirm_apply", {}, "Apply tariff limit")}
    </AdminButton>
  </div>
</Dialog>

<Dialog
  open={userDeleteOpen}
  title={at("user_delete_confirm_title", {}, "Delete user?")}
  description={at(
    "user_delete_confirm_subtitle",
    {},
    "This action is irreversible. Bot database records and the Remnawave Panel user will be deleted."
  )}
  closeLabel={at("close", {}, "Close")}
  onclose={() => usersStore.updateState({ userDeleteOpen: false })}
  class="admin-dialog admin-user-delete-dialog"
>
  <div class="admin-form-row">
    <AdminButton onclick={() => usersStore.updateState({ userDeleteOpen: false })}
      >{at("btn_cancel", {}, "Cancel")}</AdminButton
    >
    <AdminButton variant="danger" onclick={usersStore.deleteUser} disabled={userActionBusy}>
      <Trash2 size={14} />
      {at("btn_confirm_delete", {}, "Confirm deletion")}
    </AdminButton>
  </div>
</Dialog>
