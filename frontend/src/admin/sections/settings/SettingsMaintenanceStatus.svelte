<script lang="ts">
  import { AdminBadge } from "$components/patterns/admin/index.js";
  import { Clock } from "$components/ui/icons.js";
  import type { AdminSettingsSection } from "$lib/admin/settingsSections";

  let {
    at,
    sections,
  }: {
    at: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
    sections: AdminSettingsSection[];
  } = $props();
  const enabled = $derived(
    sections.some((section) =>
      section.fields.some(
        (field) => field.key === "MAINTENANCE_MODE_ENABLED" && field.value === true
      )
    )
  );
</script>

{#if enabled}
  <p role="status" class="maintenance-status">
    <AdminBadge variant="warning" wrap>
      <Clock size={14} aria-hidden="true" />
      {at("settings_maintenance_active", {}, "Maintenance mode is on")}
    </AdminBadge>
  </p>
{/if}

<style>
  .maintenance-status {
    margin: 0 0 16px;
  }
</style>
