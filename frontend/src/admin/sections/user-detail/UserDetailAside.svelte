<script lang="ts">
  import { AdminBadge, AdminButton, AdminCopyableValue } from "$components/patterns/admin/index.js";
  import { Copy, ExternalLink, UsersRound } from "$components/ui/icons.js";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState";
  import type {
    DateFormatter,
    MoneyFormatter,
    RelatedUserOpener,
    TranslateFn,
    UsersStoreBridge,
  } from "./userDetailTypes";

  let {
    at,
    usersStore,
    openedUser,
    openedUserDetail,
    openedUserAvatarUrl,
    openAvatarPreview,
    userInitials,
    userDisplayName,
    userSecondaryName,
    openUserTelegramProfile,
    openedUserTelegramProfileLink,
    openedUserTelegramProfileHint,
    fmtMoney,
    fmtDate,
    vpnLastConnectionLabel,
    referralInviter,
    referralInviteesTotal,
    openRelatedUser,
  }: {
    at: TranslateFn;
    usersStore: UsersStoreBridge;
    openedUser: AdminUser;
    openedUserDetail: AdminUserDetail;
    openedUserAvatarUrl: string;
    openAvatarPreview: () => void;
    userInitials: (user: AdminUser) => string;
    userDisplayName: (user: AdminUser) => string;
    userSecondaryName: (user: AdminUser) => string;
    openUserTelegramProfile: () => void;
    openedUserTelegramProfileLink: string;
    openedUserTelegramProfileHint: string;
    fmtMoney: MoneyFormatter;
    fmtDate: DateFormatter;
    vpnLastConnectionLabel: (detail: Record<string, unknown> | null | undefined) => string;
    referralInviter: AdminUser | null;
    referralInviteesTotal: number;
    openRelatedUser: RelatedUserOpener;
  } = $props();

  const telegramNotifications = $derived(
    openedUserDetail.telegram_notifications ?? {
      status: "unknown",
      checked_at: null,
      enabled_at: null,
      blocked_at: null,
    }
  );
  const notificationPreferences = $derived(
    openedUserDetail.notification_preferences ?? {
      marketing_email: true,
      marketing_telegram: true,
      system_email: true,
      system_telegram: true,
    }
  );

  function preferenceSummary(
    emailEnabled: boolean,
    telegramEnabled: boolean
  ): {
    label: string;
    variant: "success" | "warning" | "muted";
  } {
    if (emailEnabled && telegramEnabled) {
      return { label: at("user_notifications_on", {}, "On"), variant: "success" };
    }
    if (!emailEnabled && !telegramEnabled) {
      return { label: at("user_notifications_off", {}, "Off"), variant: "muted" };
    }
    return { label: at("user_notifications_partial", {}, "Partial"), variant: "warning" };
  }
  const marketingSummary = $derived(
    preferenceSummary(
      notificationPreferences.marketing_email,
      notificationPreferences.marketing_telegram
    )
  );
  const systemSummary = $derived(
    preferenceSummary(notificationPreferences.system_email, notificationPreferences.system_telegram)
  );
  const referralCode = $derived(
    openedUserDetail.referral?.code || openedUserDetail.user?.referral_code || ""
  );
  const userBalance = $derived(openedUserDetail.balance);
  const userBalanceAmount = $derived.by(() => {
    const amount = Number(userBalance?.amount || 0);
    return fmtMoney(Number.isFinite(amount) ? amount : 0, userBalance?.currency || "RUB");
  });
  const hwidDevicesUsageLabel = $derived.by(() => {
    const current = openedUserDetail.hwid_devices?.current_devices ?? "—";
    const max = openedUserDetail.hwid_devices?.max_devices ?? "∞";
    return at("user_hwid_devices_usage", { current, max }, "{current} of {max}");
  });

  function telegramNotificationsLabel(status: string): string {
    if (status === "blocked") {
      return at("user_bot_messages_blocked", {}, "Blocked by user");
    }
    if (status === "enabled") {
      return at("user_bot_messages_enabled", {}, "Available");
    }
    if (status === "needs_start") {
      return at("user_bot_messages_needs_start", {}, "Bot not started");
    }
    return at("user_bot_messages_unknown", {}, "Unknown");
  }

  function copyLabel(value: unknown): string {
    return at("copy_value", { value }, "Copy {value}");
  }

  function copyValue(value: string): void {
    usersStore.copyToClipboard(value, at("value_copied", {}, "Value copied"));
  }
</script>

<aside class="admin-user-aside">
  <div class="admin-user-summary">
    <button
      type="button"
      class="admin-avatar admin-avatar-lg admin-avatar-preview-trigger"
      class:is-clickable={Boolean(openedUserAvatarUrl)}
      disabled={!openedUserAvatarUrl}
      onclick={openAvatarPreview}
      aria-label={at("user_avatar_open", {}, "Open avatar")}
      title={openedUserAvatarUrl ? at("user_avatar_open", {}, "Open avatar") : ""}
    >
      {#if openedUserAvatarUrl}
        <img src={openedUserAvatarUrl} alt="" loading="lazy" referrerpolicy="no-referrer" />
      {:else}
        <span>{userInitials(openedUser)}</span>
      {/if}
    </button>
    <div class="admin-user-summary-meta">
      <strong>{userDisplayName(openedUser)}</strong>
      <small>{userSecondaryName(openedUser)}</small>
      <div class="admin-user-summary-tags">
        {#if openedUser.is_banned}
          <AdminBadge variant="danger">{at("badge_banned", {}, "Banned")}</AdminBadge>
        {:else}
          <AdminBadge variant="success">{at("badge_active", {}, "Active")}</AdminBadge>
        {/if}
        {#if openedUserDetail.active_subscription}
          <AdminBadge variant="success">{at("badge_subscription", {}, "Subscription")}</AdminBadge>
        {:else}
          <AdminBadge variant="muted"
            >{at("badge_no_subscription", {}, "No subscription")}</AdminBadge
          >
        {/if}
        {#if telegramNotifications.status === "blocked"}
          <AdminBadge variant="danger">{at("badge_bot_blocked", {}, "Bot blocked")}</AdminBadge>
        {/if}
        <AdminBadge variant={marketingSummary.variant}
          >{at("user_notifications_marketing_short", {}, "Marketing")}: {marketingSummary.label}</AdminBadge
        >
        <AdminBadge variant={systemSummary.variant}
          >{at("user_notifications_system_short", {}, "System")}: {systemSummary.label}</AdminBadge
        >
      </div>
      <div class="admin-user-summary-actions">
        {#if openedUserDetail.panel_user_url}
          <a
            class="admin-btn admin-btn-sm admin-btn-ghost"
            data-admin-action="open-remnawave-user"
            href={openedUserDetail.panel_user_url}
            target="_blank"
            rel="noreferrer noopener"
            title={at("user_open_remnawave_profile_hint", {}, "Open user card in Remnawave Panel")}
            aria-label={at("user_open_remnawave_profile", {}, "Open in Remnawave")}
          >
            <ExternalLink size={14} />
            {at("user_open_remnawave_profile", {}, "Open in Remnawave")}
          </a>
        {/if}
        <AdminButton
          size="sm"
          variant="ghost"
          onclick={openUserTelegramProfile}
          disabled={!openedUserTelegramProfileLink}
          title={openedUserTelegramProfileHint}
          aria-label={at("user_open_tg_profile", {}, "Open Telegram")}
        >
          <ExternalLink size={14} />
          {at("user_open_tg_profile", {}, "Open Telegram")}
        </AdminButton>
      </div>
    </div>
  </div>

  <div class="admin-user-stats">
    <div class="admin-user-stat">
      <span>{at("user_label_paid", {}, "Total Paid")}</span>
      <strong>{fmtMoney(openedUserDetail.total_paid)}</strong>
    </div>
    <div class="admin-user-stat">
      <span>{at("user_label_logs", {}, "Logs")}</span>
      <strong>{openedUserDetail.log_count}</strong>
    </div>
    <div class="admin-user-stat">
      <span>{at("user_label_hwid_devices", {}, "HWID devices")}</span>
      <strong>{hwidDevicesUsageLabel}</strong>
    </div>
    {#if userBalance?.enabled}
      <div class="admin-user-stat">
        <span>{at("user_label_balance", {}, "Balance")}</span>
        <strong>{userBalanceAmount}</strong>
      </div>
    {/if}
  </div>

  <div class="admin-subsection-title">{at("user_section_profile", {}, "Profile")}</div>
  <ul class="admin-meta-list">
    <li>
      <span>ID</span>
      <strong>
        <AdminCopyableValue
          value={openedUser.user_id}
          copyLabel={copyLabel(openedUser.user_id)}
          kind="user-id"
          oncopy={copyValue}
        />
      </strong>
    </li>
    <li>
      <span>Telegram ID</span>
      <strong>
        {#if openedUser.telegram_id}
          <AdminCopyableValue
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
      <span>Username</span>
      <strong>
        {#if openedUser.username}
          <AdminCopyableValue
            value={`@${openedUser.username}`}
            copyLabel={copyLabel(`@${openedUser.username}`)}
            kind="username"
            oncopy={copyValue}
          />
        {:else}
          —
        {/if}
      </strong>
    </li>
    <li>
      <span>Email</span>
      <strong class="admin-meta-truncate">
        {#if openedUser.email}
          <AdminCopyableValue
            value={openedUser.email}
            copyLabel={copyLabel(openedUser.email)}
            kind="email"
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
      <span>{at("user_label_bot_messages", {}, "Bot messages")}</span><strong
        >{telegramNotificationsLabel(
          telegramNotifications.status
        )}{#if telegramNotifications.status === "blocked" && telegramNotifications.blocked_at}
          · {fmtDate(telegramNotifications.blocked_at)}{/if}</strong
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
          <small>ID {referralInviter.user_id}</small>
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

  {#if openedUserDetail.subscription_url || openedUserDetail.install_share_url || openedUserDetail.referral?.bot_link || openedUserDetail.referral?.webapp_link}
    <div class="admin-subsection-title">{at("user_section_links", {}, "Links")}</div>
    <div class="admin-link-list">
      {#if openedUserDetail.subscription_url}
        <div class="admin-link-row">
          <div class="admin-link-row-meta">
            <span class="admin-link-row-label">{at("status_subscription", {}, "Subscription")}</span
            >
            <a
              class="admin-link-row-url"
              href={openedUserDetail.subscription_url}
              target="_blank"
              rel="noopener"
            >
              {openedUserDetail.subscription_url}
            </a>
          </div>
          <AdminButton
            size="icon"
            variant="icon"
            title={at("user_copy_tooltip", {}, "Copy")}
            onclick={() =>
              usersStore.copyToClipboard(
                openedUserDetail.subscription_url,
                at("user_sub_link_copied", {}, "Subscription link copied")
              )}
          >
            <Copy size={14} />
          </AdminButton>
        </div>
      {/if}
      {#if openedUserDetail.install_share_url}
        <div class="admin-link-row">
          <div class="admin-link-row-meta">
            <span class="admin-link-row-label"
              >{at("user_label_install_share", {}, "Install guide")}</span
            >
            <a
              class="admin-link-row-url"
              href={openedUserDetail.install_share_url}
              target="_blank"
              rel="noopener"
            >
              {openedUserDetail.install_share_url}
            </a>
          </div>
          <AdminButton
            size="icon"
            variant="icon"
            title={at("user_copy_tooltip", {}, "Copy")}
            onclick={() =>
              usersStore.copyToClipboard(
                openedUserDetail.install_share_url,
                at("user_install_share_link_copied", {}, "Install guide link copied")
              )}
          >
            <Copy size={14} />
          </AdminButton>
        </div>
      {/if}
      {#if openedUserDetail.referral?.bot_link}
        <div class="admin-link-row">
          <div class="admin-link-row-meta">
            <span class="admin-link-row-label"
              >{at("user_label_ref_bot", {}, "Referral link (bot)")}</span
            >
            <a
              class="admin-link-row-url"
              href={openedUserDetail.referral.bot_link}
              target="_blank"
              rel="noopener"
            >
              {openedUserDetail.referral.bot_link}
            </a>
          </div>
          <AdminButton
            size="icon"
            variant="icon"
            title={at("user_copy_tooltip", {}, "Copy")}
            onclick={() =>
              usersStore.copyToClipboard(
                openedUserDetail.referral.bot_link,
                at("user_ref_link_copied", {}, "Referral link copied")
              )}
          >
            <Copy size={14} />
          </AdminButton>
        </div>
      {/if}
      {#if openedUserDetail.referral?.webapp_link}
        <div class="admin-link-row">
          <div class="admin-link-row-meta">
            <span class="admin-link-row-label"
              >{at("user_label_ref_web", {}, "Referral link (web)")}</span
            >
            <a
              class="admin-link-row-url"
              href={openedUserDetail.referral.webapp_link}
              target="_blank"
              rel="noopener"
            >
              {openedUserDetail.referral.webapp_link}
            </a>
          </div>
          <AdminButton
            size="icon"
            variant="icon"
            title={at("user_copy_tooltip", {}, "Copy")}
            onclick={() =>
              usersStore.copyToClipboard(
                openedUserDetail.referral.webapp_link,
                at("user_ref_link_copied", {}, "Referral link copied")
              )}
          >
            <Copy size={14} />
          </AdminButton>
        </div>
      {/if}
    </div>
  {/if}
</aside>
