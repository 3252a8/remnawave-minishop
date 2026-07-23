<script lang="ts">
  type Props = {
    name: string;
    secondary?: string;
    idText?: string;
    initials?: string;
    avatarUrl?: string;
  };

  let { name, secondary = "", idText = "", initials = "", avatarUrl = "" }: Props = $props();
</script>

<!-- Avatar plus name/secondary/id stack for user cells in admin tables. -->
<div class="admin-user-cell">
  <span class="admin-avatar admin-avatar-sm">
    {#if avatarUrl}
      <img src={avatarUrl} alt="" loading="lazy" referrerpolicy="no-referrer" />
    {:else}
      <span>{initials}</span>
    {/if}
  </span>
  <div class="admin-user-cell-text">
    <span class="admin-user-cell-name">{name}</span>
    {#if secondary}
      <span class="admin-user-cell-secondary">{secondary}</span>
    {/if}
    {#if idText}
      <span class="admin-user-cell-id">{idText}</span>
    {/if}
  </div>
</div>

<style>
  .admin-user-cell {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }

  .admin-user-cell-text {
    display: grid;
    gap: 2px;
    min-width: 0;
    text-align: left;
  }

  .admin-user-cell-name {
    font-weight: 650;
    font-size: 13px;
    line-height: 1.25;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-user-cell-secondary {
    font-size: 11px;
    color: var(--admin-dim);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-user-cell-id {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--admin-muted);
  }
</style>
