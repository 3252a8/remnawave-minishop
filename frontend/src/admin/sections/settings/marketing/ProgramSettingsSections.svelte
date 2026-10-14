<script lang="ts">
  import SettingsDisclosureTrigger from "../SettingsDisclosureTrigger.svelte";
  import { settingsSectionAnchorKey } from "$lib/admin/settingsSections";
  import PartnerProgramSettings from "./PartnerProgramSettings.svelte";
  import ReferralProgramSettings from "./ReferralProgramSettings.svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    at,
    highlightedSettingKey = "",
    settingsOpenSections,
    toggleSettingsSection,
    onNavigateSection = () => {},
    onOpenSettingsPath = () => {},
  }: {
    at: TranslateFn;
    highlightedSettingKey?: string;
    settingsOpenSections: string[];
    toggleSettingsSection: (sectionId: string) => void;
    onNavigateSection?: (section: string) => void;
    onOpenSettingsPath?: (path: string[]) => void;
  } = $props();

  const referralOpen = $derived(settingsOpenSections.includes("referral"));
  const partnerOpen = $derived(settingsOpenSections.includes("partner"));
</script>

<section class="admin-accordion-item admin-card">
  <SettingsDisclosureTrigger
    anchorKey={settingsSectionAnchorKey("referral")}
    contentId="admin-settings-section-referral"
    countLabel={at("marketing_programs_referral_scope", {}, "Referral settings")}
    onToggle={() => toggleSettingsSection("referral")}
    open={referralOpen}
    title={at("marketing_programs_referral", {}, "Referral program")}
  />
  {#if referralOpen}
    <div id="admin-settings-section-referral" class="admin-accordion-content" data-state="open">
      <div class="admin-settings-fields program-settings-editor">
        <ReferralProgramSettings {at} {highlightedSettingKey} />
      </div>
    </div>
  {/if}
</section>

<section class="admin-accordion-item admin-card">
  <SettingsDisclosureTrigger
    anchorKey={settingsSectionAnchorKey("partner")}
    contentId="admin-settings-section-partner"
    countLabel={at("marketing_programs_partner_scope", {}, "Partner settings")}
    onToggle={() => toggleSettingsSection("partner")}
    open={partnerOpen}
    title={at("marketing_programs_partner", {}, "Partner program")}
  />
  {#if partnerOpen}
    <div id="admin-settings-section-partner" class="admin-accordion-content" data-state="open">
      <div class="admin-settings-fields program-settings-editor">
        <PartnerProgramSettings {at} {onNavigateSection} {onOpenSettingsPath} />
      </div>
    </div>
  {/if}
</section>

<style>
  .program-settings-editor {
    padding: 14px;
  }

  @media (max-width: 700px) {
    .program-settings-editor {
      padding: 10px;
    }
  }
</style>
