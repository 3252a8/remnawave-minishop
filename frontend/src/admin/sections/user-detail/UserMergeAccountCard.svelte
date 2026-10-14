<script lang="ts">
  import { AdminBadge, AdminUserCell } from "$components/patterns/admin/index.js";
  import {
    userAvatarUrl,
    userDisplayName,
    userInitials,
    userSecondaryName,
  } from "$lib/admin/users.js";
  import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState.js";
  import type { UserMergeContext } from "$lib/admin/userMergeApi.js";
  import type { DateFormatter, TranslateFn } from "./userDetailTypes.js";

  let {
    detail,
    context,
    retained,
    at,
    fmtDate,
  }: {
    detail: AdminUserDetail;
    context: UserMergeContext;
    retained: boolean;
    at: TranslateFn;
    fmtDate: DateFormatter;
  } = $props();
  const subscription = $derived(detail.active_subscription);
  const identities = $derived([
    ...context.auth_identities.map(
      (identity) => `${identity.provider}${identity.email ? ` · ${identity.email}` : ""}`
    ),
    ...(context.password_available ? [at("user_merge_password")] : []),
    ...(context.passkey_count ? [at("user_merge_passkeys", { count: context.passkey_count })] : []),
  ]);
</script>

<section class="merge-account" data-retained={retained} data-user-id={detail.user.user_id}>
  <div class="merge-account-badges">
    <AdminBadge variant={retained ? "success" : "warning"}
      >{at(retained ? "user_merge_retained" : "user_merge_removed")}</AdminBadge
    >
    <AdminBadge variant={detail.user.is_banned ? "danger" : "success"}
      >{at(detail.user.is_banned ? "badge_banned" : "badge_active")}</AdminBadge
    >
    {#if !context.merge_eligibility.allowed}<AdminBadge variant="danger"
        >{at("user_merge_restricted")}</AdminBadge
      >{/if}
  </div>
  <AdminUserCell
    name={userDisplayName(detail.user)}
    secondary={userSecondaryName(detail.user)}
    initials={userInitials(detail.user)}
    avatarUrl={userAvatarUrl(detail.user)}
  />
  <div class="merge-account-id">
    {detail.user.minishop_id || "—"} · {at("user_merge_internal_id")}: {detail.user.user_id}
  </div>
  <dl>
    <div>
      <dt>{at("user_merge_telegram")}</dt>
      <dd>
        {detail.user.telegram_id
          ? `${detail.user.username ? `@${detail.user.username} · ` : ""}${detail.user.telegram_id}`
          : "—"}
      </dd>
    </div>
    <div>
      <dt>{at("user_merge_email")}</dt>
      <dd>
        {[...new Set([detail.user.email, ...context.verified_emails].filter(Boolean))].join(", ") ||
          "—"}
      </dd>
    </div>
    <div>
      <dt>{at("user_merge_logins")}</dt>
      <dd>{identities.join("; ") || at("user_merge_no_extra_logins")}</dd>
    </div>
    <div>
      <dt>{at("user_merge_balance")}</dt>
      <dd>
        {detail.balance?.enabled
          ? `${detail.balance.amount} ${detail.balance.currency}`
          : at("user_merge_balance_disabled")}
      </dd>
    </div>
    <div>
      <dt>{at("user_merge_subscription")}</dt>
      <dd>
        {subscription?.display_label ||
          subscription?.tariff_key ||
          at("badge_no_subscription")}{#if subscription?.end_date}<br />{at("user_merge_until", {
            date: fmtDate(subscription.end_date),
          })}{/if}<br /><small
          >{at("user_merge_subscriptions_count", { count: detail.subscriptions.length })}</small
        >
      </dd>
    </div>
  </dl>
  {#if !context.merge_eligibility.allowed}<p class="merge-account-restriction">
      {at(
        context.merge_eligibility.reason === "account_merge_banned"
          ? "user_merge_banned"
          : context.merge_eligibility.reason === "account_merge_current_admin"
            ? "user_merge_current_admin"
            : "user_merge_protected"
      )}
    </p>{/if}
</section>

<style>
  .merge-account {
    display: grid;
    align-content: start;
    gap: 10px;
    min-width: 0;
    padding: 14px;
    border: 1px solid var(--admin-border);
    border-radius: var(--radius-card);
    background: var(--admin-surface-2);
  }
  .merge-account-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .merge-account-id {
    font-size: 12px;
    color: var(--admin-muted);
    overflow-wrap: anywhere;
  }
  dl {
    display: grid;
    gap: 8px;
    margin: 0;
    font-size: 12px;
  }
  dl > div {
    display: grid;
    grid-template-columns: minmax(74px, 0.65fr) minmax(0, 1.35fr);
    gap: 8px;
  }
  dt,
  small {
    color: var(--admin-muted);
  }
  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .merge-account-restriction {
    margin: 0;
    font-size: 12px;
    color: var(--danger);
  }
  @media (max-width: 600px) {
    .merge-account {
      padding: 12px;
      gap: 8px;
    }
    dl {
      gap: 6px;
    }
  }
</style>
