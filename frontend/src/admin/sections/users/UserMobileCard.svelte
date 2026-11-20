<script lang="ts">
  import { UsersRound } from "$components/ui/icons.js";
  import {
    AdminBadge,
    AdminUserCell,
    AdminSubscriptionPlan,
  } from "$components/patterns/admin/index.js";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import type { AdminUserExtensionColumn } from "$lib/admin/stores/usersStoreState";
  import type { AdminBadgeVariant } from "$components/patterns/admin/types";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type TrafficBadge =
    | {
        state?: string;
        used_bytes?: number | string | null;
        limit_bytes?: number | string | null;
      }
    | null
    | undefined;

  let {
    at,
    currentLang,
    user,
    onopen,
    resolvedAvatarUrl,
    panelStatusBadge,
    userInitials,
    userDisplayName,
    userSecondaryName,
    premiumTrafficBadgeVariant,
    premiumTrafficBadgeText,
    rowPaymentsTotal,
    rowBalance,
    userBalanceEnabled,
    partnerBalanceEnabled,
    extensionColumns,
    fmtDateShort,
  }: {
    at: TranslateFn;
    currentLang: string;
    user: AdminUser;
    onopen: () => void;
    resolvedAvatarUrl: (user: AdminUser) => string;
    panelStatusBadge: (user: AdminUser) => { label?: string; variant?: AdminBadgeVariant };
    userInitials: (user: AdminUser) => string;
    userDisplayName: (user: AdminUser) => string;
    userSecondaryName: (user: AdminUser) => string;
    premiumTrafficBadgeVariant: (pt: TrafficBadge) => AdminBadgeVariant;
    premiumTrafficBadgeText: (pt: TrafficBadge) => string;
    rowPaymentsTotal: (user: AdminUser) => string;
    rowBalance: (user: AdminUser, source: "user" | "partner") => string;
    userBalanceEnabled: boolean;
    partnerBalanceEnabled: boolean;
    extensionColumns: AdminUserExtensionColumn[];
    fmtDateShort: (value: string | null | undefined) => string;
  } = $props();

  const avatar = $derived(resolvedAvatarUrl(user));
  const badge = $derived(panelStatusBadge(user));
  const expires = $derived(
    fmtDateShort(user.subscription_expires_at || user.panel_status_expired_at)
  );
  const paymentsCount = $derived(Number(user.payments_count ?? 0));
  const invitedCount = $derived(Number(user.invited_users_count ?? 0));
  const hasPremium = $derived(
    Boolean(user.premium_traffic && user.premium_traffic.state !== "none")
  );

  function handleKeydown(event: KeyboardEvent): void {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    onopen();
  }
</script>

<!-- Two lines instead of a label grid: who and status, plan and term, then only
     the facts this user actually has. Tap opens the full card. -->
<li>
  <div
    class="admin-user-mobile-card"
    role="button"
    tabindex="0"
    data-mobile-user-id={user.user_id}
    onclick={onopen}
    onkeydown={handleKeydown}
  >
    <div class="admin-user-mobile-head">
      <AdminUserCell
        name={userDisplayName(user)}
        secondary={userSecondaryName(user)}
        idText={user.minishop_id || ""}
        initials={userInitials(user)}
        avatarUrl={avatar}
      />
      <AdminBadge variant={badge.variant}>{badge.label}</AdminBadge>
    </div>

    <div class="admin-user-mobile-plan">
      <AdminSubscriptionPlan plan={user.subscription_plan} {at} {currentLang} />
      {#if expires && expires !== "—"}
        <span class="admin-user-mobile-term"
          >{at("users_col_subscription_expires", {}, "Expires")} {expires}</span
        >
      {/if}
    </div>

    <ul class="admin-user-mobile-facts">
      {#if paymentsCount > 0}
        <li>
          <span>{at("users_col_payments_total", {}, "Paid total")}</span>
          <strong>{rowPaymentsTotal(user)}</strong>
        </li>
        <li>
          <span>{at("users_col_payments_count", {}, "Payments")}</span>
          <strong>{paymentsCount}</strong>
        </li>
      {/if}
      {#if userBalanceEnabled}
        <li>
          <span>{at("users_col_user_balance", {}, "Balance")}</span>
          <strong>{rowBalance(user, "user")}</strong>
        </li>
      {/if}
      {#if partnerBalanceEnabled}
        <li>
          <span>{at("users_col_partner_balance", {}, "Partner balance")}</span>
          <strong>{rowBalance(user, "partner")}</strong>
        </li>
      {/if}
      {#if invitedCount > 0}
        <li>
          <UsersRound size={12} />
          <span>{at("users_col_invited", {}, "Invited")}</span>
          <strong>{invitedCount}</strong>
        </li>
      {/if}
      {#if hasPremium}
        <li>
          <AdminBadge
            variant={premiumTrafficBadgeVariant(user.premium_traffic)}
            class="admin-user-premium-badge"
          >
            {premiumTrafficBadgeText(user.premium_traffic)}
          </AdminBadge>
        </li>
      {/if}
      {#each extensionColumns as column (column.id)}
        <li class="admin-user-mobile-extension">
          <span>{column.label}</span>
          <strong>{user.extension_values?.[column.id] ?? "—"}</strong>
        </li>
      {/each}
      <li class="admin-user-mobile-registered">
        <span>{at("users_col_registration", {}, "Registered")}</span>
        <strong>{fmtDateShort(user.registration_date)}</strong>
      </li>
    </ul>
  </div>
</li>

<style>
  .admin-user-mobile-card {
    display: grid;
    gap: 8px;
    min-width: 0;
    padding: 12px;
    border: 1px solid var(--admin-border);
    border-radius: 12px;
    background: var(--admin-surface-2);
    cursor: pointer;
  }

  .admin-user-mobile-card:hover {
    border-color: color-mix(in srgb, var(--admin-border) 65%, var(--accent));
  }

  .admin-user-mobile-card:focus-visible {
    outline: 2px solid var(--admin-ring);
    outline-offset: 2px;
  }

  .admin-user-mobile-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    min-width: 0;
  }

  .admin-user-mobile-head :global(.admin-user-cell) {
    flex: 1 1 auto;
  }

  .admin-user-mobile-head :global(.admin-badge) {
    flex: 0 0 auto;
  }

  .admin-user-mobile-plan {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 4px 10px;
    min-width: 0;
    font-size: 13px;
  }

  .admin-user-mobile-term {
    color: var(--admin-muted);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }

  .admin-user-mobile-facts {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 14px;
    min-width: 0;
    margin: 0;
    padding: 8px 0 0;
    border-top: 1px solid var(--admin-border);
    list-style: none;
    font-size: 12px;
  }

  .admin-user-mobile-facts li {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    min-width: 0;
    color: var(--admin-muted);
  }

  .admin-user-mobile-facts strong {
    color: var(--admin-text);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .admin-user-mobile-facts :global(.admin-user-premium-badge) {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-user-mobile-registered {
    margin-left: auto;
  }

  .admin-user-mobile-extension {
    flex-wrap: wrap;
    overflow-wrap: anywhere;
  }
</style>
