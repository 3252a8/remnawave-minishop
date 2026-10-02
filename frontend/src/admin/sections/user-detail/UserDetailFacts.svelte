<script lang="ts">
  import { AdminButton, AdminCopyableValue } from "$components/patterns/admin/index.js";
  import { ExternalLink, UsersRound } from "$components/ui/icons.js";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState";
  import type {
    DateFormatter,
    RelatedUserOpener,
    TranslateFn,
    UsersStoreBridge,
  } from "./userDetailTypes";
  let {
    at,
    usersStore,
    openedUser,
    openedUserDetail,
    userDisplayName,
    fmtDate,
    vpnLastConnectionLabel,
    referralInviter,
    referralInviteesTotal,
    openRelatedUser,
    onOpenPartnerCard,
  }: {
    at: TranslateFn;
    usersStore: UsersStoreBridge;
    openedUser: AdminUser;
    openedUserDetail: AdminUserDetail;
    userDisplayName: (user: AdminUser) => string;
    fmtDate: DateFormatter;
    vpnLastConnectionLabel: (detail: Record<string, unknown> | null | undefined) => string;
    referralInviter: AdminUser | null;
    referralInviteesTotal: number;
    openRelatedUser: RelatedUserOpener;
    onOpenPartnerCard: (partnerId: string) => void;
  } = $props();
  const referralCode = $derived(
    openedUserDetail.referral?.code || openedUserDetail.user?.referral_code || ""
  );
  const partnerAttribution = $derived(openedUserDetail.partner_attribution);
  function copyLabel(value: unknown): string {
    return at("copy_value", { value }, "Copy {value}");
  }
  function copyValue(value: string): void {
    usersStore.copyToClipboard(value, at("value_copied", {}, "Value copied"));
  }
</script>

<ul class="admin-meta-list admin-user-facts">
  {#if openedUser.panel_username && openedUser.panel_username !== openedUser.minishop_id}
    <li>
      <span>{at("user_panel_username", {}, "Panel username")}</span>
      <strong>
        <AdminCopyableValue
          wrap
          value={openedUser.panel_username}
          copyLabel={copyLabel(openedUser.panel_username)}
          kind="username"
          oncopy={copyValue}
        />
      </strong>
    </li>
  {/if}
  <li>
    <span>{at("user_telegram_id", {}, "Telegram ID")}</span>
    <strong>
      {#if openedUser.telegram_id}
        <AdminCopyableValue
          wrap
          value={openedUser.telegram_id}
          copyLabel={copyLabel(openedUser.telegram_id)}
          kind="telegram-id"
          oncopy={copyValue}
        />
      {:else}
        —
      {/if}
    </strong>
  </li>

  <li>
    <span>{at("user_label_registration", {}, "Registration")}</span><strong
      >{fmtDate(openedUser.registration_date)}</strong
    >
  </li>

  <li>
    <span>{at("user_label_vpn_last_connected", {}, "Last VPN connection")}</span><strong
      >{vpnLastConnectionLabel(openedUserDetail)}</strong
    >
  </li>
  <li>
    <span>{at("user_label_ref_code", {}, "Referral Code")}</span>
    <strong>
      {#if referralCode}
        <AdminCopyableValue
          wrap
          value={referralCode}
          copyLabel={copyLabel(referralCode)}
          kind="referral-code"
          oncopy={copyValue}
        />
      {:else}
        —
      {/if}
    </strong>
  </li>
  <li class="admin-user-ref-row">
    <span>{at("user_label_invited_by", {}, "Invited by")}</span>
    <strong class="admin-user-ref-value">
      {#if referralInviter}
        <span>{userDisplayName(referralInviter)}</span>
        <small>ID {referralInviter.minishop_id || "—"}</small>
      {:else}
        <span>{at("user_invited_by_none", {}, "—")}</span>
      {/if}
    </strong>
    {#if referralInviter}
      <AdminButton
        size="icon"
        variant="icon"
        title={at("user_open_related", {}, "Open user card")}
        aria-label={at("user_open_related", {}, "Open user card")}
        onclick={() => openRelatedUser(referralInviter)}
      >
        <ExternalLink size={14} />
      </AdminButton>
    {/if}
  </li>
  {#if partnerAttribution}
    <li class="admin-user-ref-row">
      <span>{at("user_label_partner_attribution", {}, "Partner attribution")}</span>
      <strong class="admin-user-ref-value">
        <span>{partnerAttribution.display_label}</span>
        <small>
          ID {partnerAttribution.partner_id} · {at("user_partner_client_id", {}, "Client")}
          {partnerAttribution.public_client_id}
        </small>
      </strong>
      <AdminButton
        size="icon"
        variant="icon"
        title={at("user_open_partner", {}, "Open partner card")}
        aria-label={at("user_open_partner", {}, "Open partner card")}
        onclick={() => onOpenPartnerCard(String(partnerAttribution.partner_id))}
      >
        <ExternalLink size={14} />
      </AdminButton>
    </li>
  {/if}
  <li class="admin-user-ref-row">
    <span>{at("user_label_invited_users", {}, "Invited users")}</span>
    <strong>{referralInviteesTotal}</strong>
    <AdminButton
      data-admin-action="open-user-referrals"
      size="sm"
      variant="ghost"
      disabled={referralInviteesTotal <= 0}
      onclick={() => usersStore.openUserReferrals(0)}
    >
      <UsersRound size={14} />
      {at("user_invitees_open", {}, "Show")}
    </AdminButton>
  </li>
</ul>
