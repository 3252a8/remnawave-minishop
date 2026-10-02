<script lang="ts">
  import { AdminBadge, AdminButton, AdminCopyableValue } from "$components/patterns/admin/index.js";
  import { Copy, ExternalLink } from "$components/ui/icons.js";
  import type { Snippet } from "svelte";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState";
  import type { DateFormatter, TranslateFn, UsersStoreBridge } from "./userDetailTypes";

  let {
    at,
    usersStore,
    openedUser,
    openedUserDetail,
    openedUserAvatarUrl,
    openAvatarPreview,
    userInitials,
    userDisplayName,
    fmtDate,
    details,
    openUserTelegramProfile,
    openedUserTelegramProfileLink,
    openedUserTelegramProfileHint,
  }: {
    at: TranslateFn;
    usersStore: UsersStoreBridge;
    openedUser: AdminUser;
    openedUserDetail: AdminUserDetail | null;
    openedUserAvatarUrl: string;
    openAvatarPreview: () => void;
    userInitials: (user: AdminUser) => string;
    userDisplayName: (user: AdminUser) => string;
    fmtDate: DateFormatter;
    details?: Snippet;
    openUserTelegramProfile: () => void;
    openedUserTelegramProfileLink: string;
    openedUserTelegramProfileHint: string;
  } = $props();

  let failedAvatarUrl = $state("");
  let heading = $state<HTMLHeadingElement>();
  const visibleAvatarUrl = $derived(
    openedUserAvatarUrl !== failedAvatarUrl ? openedUserAvatarUrl : ""
  );
  const identity = $derived(openedUser.minishop_id || String(openedUser.user_id));
  $effect(() => {
    void identity;
    heading?.focus({ preventScroll: true });
  });

  const telegramStatus = $derived(openedUserDetail?.telegram_notifications?.status || "unknown");
  const displayName = $derived(userDisplayName(openedUser));
  const contacts = $derived(
    [
      { kind: "username", value: openedUser.username ? `@${openedUser.username}` : "" },
      { kind: "email", value: openedUser.email || "" },
    ].filter((contact) => contact.value)
  );
  const primaryContact = $derived(contacts.find((contact) => contact.value === displayName));
  function copyValue(value: string): void {
    usersStore.copyToClipboard(value, at("value_copied", {}, "Value copied"));
  }
</script>

<header class="admin-user-hero">
  <button
    type="button"
    class="admin-avatar admin-avatar-lg admin-avatar-preview-trigger"
    class:is-clickable={Boolean(visibleAvatarUrl)}
    disabled={!visibleAvatarUrl}
    onclick={openAvatarPreview}
    aria-label={at("user_avatar_open", {}, "Open avatar")}
  >
    {#if visibleAvatarUrl}
      <img
        src={visibleAvatarUrl}
        alt=""
        referrerpolicy="no-referrer"
        onerror={() => (failedAvatarUrl = openedUserAvatarUrl)}
      />
    {:else}
      <span>{userInitials(openedUser)}</span>
    {/if}
  </button>
  <div class="admin-user-hero-identity">
    <div class="admin-user-hero-name">
      <h2 bind:this={heading} tabindex="-1">{displayName}</h2>
      {#if primaryContact}
        <AdminButton
          size="icon"
          variant="icon"
          title={at("copy_value", { value: primaryContact.value }, "Copy {value}")}
          onclick={() => copyValue(primaryContact!.value)}
        >
          <Copy size={14} />
        </AdminButton>
      {/if}
    </div>
    {#if contacts.some((contact) => contact.value !== displayName)}
      <div class="admin-user-hero-contacts">
        {#each contacts.filter((contact) => contact.value !== displayName) as contact (contact.kind)}
          <AdminCopyableValue
            wrap
            value={contact.value}
            kind={contact.kind}
            copyLabel={at("copy_value", { value: contact.value }, "Copy {value}")}
            oncopy={copyValue}
          />
        {/each}
      </div>
    {/if}
    {#if openedUser.minishop_id}
      <AdminCopyableValue
        wrap
        value={openedUser.minishop_id}
        copyLabel={at("copy_value", { value: openedUser.minishop_id }, "Copy {value}")}
        kind="user-id"
        oncopy={copyValue}
      />
    {/if}
    {#if openedUserDetail}
      <div class="admin-user-summary-tags">
        <AdminBadge variant={openedUser.is_banned ? "danger" : "success"}>
          {openedUser.is_banned
            ? at("badge_banned", {}, "Banned")
            : at("badge_active", {}, "Active")}
        </AdminBadge>
        <AdminBadge variant={openedUserDetail.active_subscription ? "success" : "muted"}>
          {openedUserDetail.active_subscription
            ? at("badge_subscription", {}, "Subscription")
            : at("badge_no_subscription", {}, "No subscription")}
        </AdminBadge>
        {#if openedUser.telegram_id}
          <AdminBadge
            variant={telegramStatus === "blocked"
              ? "danger"
              : telegramStatus === "enabled"
                ? "success"
                : "muted"}
          >
            {at("user_label_bot_messages", {}, "Bot messages")}: {telegramStatus === "blocked"
              ? at("badge_bot_blocked", {}, "Bot blocked")
              : telegramStatus === "enabled"
                ? at("user_bot_messages_enabled", {}, "Available")
                : telegramStatus === "needs_start"
                  ? at("user_bot_messages_needs_start", {}, "Bot not started")
                  : at("user_bot_messages_unknown", {}, "Unknown")}
            {#if telegramStatus === "blocked" && openedUserDetail.telegram_notifications?.blocked_at}
              · {fmtDate(openedUserDetail.telegram_notifications.blocked_at)}
            {/if}
          </AdminBadge>
        {/if}
      </div>
    {/if}
  </div>
  <div class="admin-user-hero-actions">
    {#if openedUserDetail?.panel_user_url}
      <a
        class="admin-btn admin-btn-sm admin-btn-ghost"
        data-admin-action="open-remnawave-user"
        href={openedUserDetail.panel_user_url}
        target="_blank"
        rel="noreferrer noopener"
        title={at("user_open_remnawave_profile_hint", {}, "Open user card in Remnawave Panel")}
      >
        <ExternalLink size={14} />{at("user_open_remnawave_profile", {}, "Open in Remnawave")}
      </a>
    {/if}
    <AdminButton
      size="sm"
      variant="ghost"
      onclick={openUserTelegramProfile}
      disabled={!openedUserTelegramProfileLink}
      title={openedUserTelegramProfileHint}
    >
      <ExternalLink size={14} />{at("user_open_tg_profile", {}, "Open Telegram")}
    </AdminButton>
  </div>
  {#if openedUserDetail && details}
    <div class="admin-user-hero-facts">{@render details()}</div>
  {/if}
</header>
