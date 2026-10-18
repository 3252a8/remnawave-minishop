<script lang="ts">
  import { AdminUserCell } from "$components/patterns/admin/index.js";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import type { TranslateFn } from "$lib/admin/stores/usersStoreState";

  let {
    user,
    at,
    resolvedAvatarUrl,
    userDisplayName,
    userInitials,
    expanded = false,
  }: {
    user: AdminUser;
    at: TranslateFn;
    resolvedAvatarUrl: (user: AdminUser) => string;
    userDisplayName: (user: AdminUser) => string;
    userInitials: (user: AdminUser) => string;
    expanded?: boolean;
  } = $props();

  const fields = $derived([
    [at("relationships_ms_uuid", {}, "MS UUID"), user.minishop_id],
    [at("user_telegram_id", {}, "Telegram ID"), user.telegram_id],
    [at("relationships_username", {}, "TG username"), user.username ? `@${user.username}` : null],
    [at("relationships_email", {}, "Email"), user.email],
  ]);
</script>

<div class="relationship-user" class:expanded>
  <AdminUserCell
    name={userDisplayName(user)}
    initials={userInitials(user)}
    avatarUrl={resolvedAvatarUrl(user)}
  >
    {#snippet details()}
      <dl>
        {#each fields as [label, value] (label)}
          <div>
            <dt>{label}</dt>
            <dd title={String(value ?? "—")}>{value ?? "—"}</dd>
          </div>
        {/each}
      </dl>
    {/snippet}
  </AdminUserCell>
</div>

<style>
  .relationship-user {
    min-width: 0;
    width: 100%;
    text-align: left;
  }
  dl {
    display: grid;
    gap: 3px;
    margin: 5px 0 0;
  }
  dl > div {
    display: grid;
    grid-template-columns: 68px minmax(0, 1fr);
    gap: 6px;
  }
  dt {
    color: var(--admin-muted);
    font-size: 10px;
    line-height: 13px;
  }
  dd {
    margin: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 10px;
    line-height: 13px;
    font-family: var(--font-mono);
  }
  .expanded dd {
    white-space: normal;
    overflow-wrap: anywhere;
    font-size: 12px;
    line-height: 16px;
  }
  .expanded dt {
    font-size: 11px;
    line-height: 16px;
  }
  .expanded dl {
    gap: 5px;
    margin-top: 8px;
  }
  .expanded dl > div {
    grid-template-columns: 80px minmax(0, 1fr);
  }
  .expanded :global(.admin-user-cell-name) {
    white-space: normal;
    overflow-wrap: anywhere;
  }
</style>
