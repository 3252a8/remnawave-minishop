<script lang="ts">
  import { AdminBadge } from "$components/patterns/admin/index.js";
  import { Clock } from "$components/ui/icons.js";
  let {
    at,
    enabled,
    banner = false,
  }: {
    at: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
    enabled: boolean;
    banner?: boolean;
  } = $props();
</script>

{#if enabled}
  <p role="status" class={["maintenance-status", { banner }]}>
    <AdminBadge variant="warning" wrap>
      <Clock size={banner ? 18 : 14} aria-hidden="true" />
      {at("settings_maintenance_active", {}, "Maintenance mode is on")}
    </AdminBadge>
  </p>
{/if}

<style>
  .maintenance-status {
    margin: 0 0 16px;
  }

  .banner :global(.admin-badge) {
    display: flex;
    gap: 8px;
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 14px;
  }
</style>
