<script lang="ts">
  import { DollarSign, UsersRound } from "$components/ui/icons.js";
  import { AdminBadge, AdminUserCell } from "$components/patterns/admin/index.js";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
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
    fmtDateShort,
  }: {
    at: TranslateFn;
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
    fmtDateShort: (value: string | null | undefined) => string;
  } = $props();

  const avatar = $derived(resolvedAvatarUrl(user));
  const badge = $derived(panelStatusBadge(user));

  function handleKeydown(event: KeyboardEvent): void {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    onopen();
  }
</script>

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
        idText={`#${user.user_id}`}
        initials={userInitials(user)}
        avatarUrl={avatar}
      />
      <AdminBadge variant={badge.variant}>{badge.label}</AdminBadge>
    </div>

    <dl class="admin-user-mobile-metrics">
      {#if userBalanceEnabled}
        <div>
          <dt>{at("users_col_user_balance", {}, "Balance")}</dt>
          <dd class="admin-user-balance-value">{rowBalance(user, "user")}</dd>
        </div>
      {/if}
      {#if partnerBalanceEnabled}
        <div>
          <dt>{at("users_col_partner_balance", {}, "Partner balance")}</dt>
          <dd class="admin-user-balance-value">{rowBalance(user, "partner")}</dd>
        </div>
      {/if}
      <div>
        <dt>{at("premium_traffic_filter_label", {}, "Premium traffic")}</dt>
        <dd>
          {#if user.premium_traffic && user.premium_traffic.state !== "none"}
            <AdminBadge
              variant={premiumTrafficBadgeVariant(user.premium_traffic)}
              class="admin-user-premium-badge"
            >
              {premiumTrafficBadgeText(user.premium_traffic)}
            </AdminBadge>
          {:else}
            <span class="admin-user-premium-placeholder">{at("premium_traffic_na", {}, "—")}</span>
          {/if}
        </dd>
      </div>
      <div>
        <dt>{at("users_col_payments_total", {}, "Paid total")}</dt>
        <dd>
          <AdminBadge variant="success" class="admin-user-money-badge">
            {rowPaymentsTotal(user)}
          </AdminBadge>
        </dd>
      </div>
      <div>
        <dt>{at("users_col_payments_count", {}, "Payments")}</dt>
        <dd class="admin-user-counter">
          <DollarSign size={12} />
          <span>{user.payments_count ?? 0}</span>
        </dd>
      </div>
      <div>
        <dt>{at("users_col_invited", {}, "Invited")}</dt>
        <dd class="admin-user-counter">
          <UsersRound size={13} />
          <span>{user.invited_users_count ?? 0}</span>
        </dd>
      </div>
    </dl>

    <dl class="admin-user-mobile-dates">
      <div>
        <dt>{at("users_col_subscription_expires", {}, "Expires")}</dt>
        <dd>{fmtDateShort(user.subscription_expires_at || user.panel_status_expired_at)}</dd>
      </div>
      <div>
        <dt>{at("users_col_registration", {}, "Registered")}</dt>
        <dd>{fmtDateShort(user.registration_date)}</dd>
      </div>
    </dl>
  </div>
</li>

<style>
  .admin-user-mobile-card {
    display: grid;
    gap: 10px;
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

  .admin-user-mobile-metrics {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    min-width: 0;
    margin: 0;
  }

  .admin-user-mobile-metrics > div {
    display: grid;
    align-content: start;
    gap: 4px;
    min-width: 0;
    min-height: 56px;
    padding: 8px 9px;
    border-radius: 8px;
    background: color-mix(in srgb, var(--admin-bg) 58%, transparent);
  }

  .admin-user-mobile-metrics dt,
  .admin-user-mobile-dates dt {
    overflow: hidden;
    color: var(--admin-muted);
    font-size: 10px;
    font-weight: 650;
    letter-spacing: 0.04em;
    text-overflow: ellipsis;
    text-transform: uppercase;
    white-space: nowrap;
  }

  .admin-user-mobile-metrics dd,
  .admin-user-mobile-dates dd {
    min-width: 0;
    margin: 0;
    color: var(--admin-text);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }

  .admin-user-mobile-metrics dd :global(.admin-badge) {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-user-mobile-metrics .admin-user-balance-value {
    overflow: hidden;
    font-weight: 750;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-user-mobile-dates {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    min-width: 0;
    margin: 0;
    padding-top: 10px;
    border-top: 1px solid var(--admin-border);
  }

  .admin-user-mobile-dates > div {
    display: grid;
    gap: 3px;
    min-width: 0;
  }

  .admin-user-mobile-dates > div:last-child {
    text-align: right;
  }

  .admin-user-mobile-dates dd {
    overflow: hidden;
    color: var(--admin-muted);
    font-family: var(--font-mono);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
