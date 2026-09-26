<script lang="ts">
  import SettingsDisclosureTrigger from "./SettingsDisclosureTrigger.svelte";
  import RoleManagement from "./RoleManagement.svelte";
  import { settingsSubsectionAnchorKey } from "$lib/admin/settingsSections";

  let {
    at,
    contentId,
    open,
    onToggle,
  }: {
    at: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
    contentId: string;
    open: boolean;
    onToggle: () => void;
  } = $props();
</script>

<div class="admin-subsection-accordion">
  <section class="admin-settings-subsection">
    <SettingsDisclosureTrigger
      anchorKey={settingsSubsectionAnchorKey("general", "administrators")}
      {contentId}
      countLabel=""
      level="subsection"
      {onToggle}
      {open}
      title={at("roles_title", {}, "Administrators")}
    />
    {#if open}
      <div id={contentId} class="admin-accordion-content" data-state="open">
        <RoleManagement {at} />
      </div>
    {/if}
  </section>
</div>
