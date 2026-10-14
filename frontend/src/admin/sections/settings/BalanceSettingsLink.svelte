<script lang="ts">
  import { ArrowRight } from "$components/ui/icons.js";
  import { AdminButton, AdminSettingCard } from "$components/patterns/admin/index.js";

  let {
    at,
    destination = "partner",
    onOpenSettingsPath,
  }: {
    at: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
    destination?: "partner" | "balance";
    onOpenSettingsPath: (path: string[]) => void;
  } = $props();
</script>

<AdminSettingCard
  title={at("settings_balance_sources_title", {}, "Two funds sources")}
  description={at(
    destination === "partner" ? "settings_balance_sources_hint" : "settings_partner_balance_hint",
    {},
    destination === "partner"
      ? "Personal and partner balances share the checkout card. Partner spending follows the partner program rules."
      : "Recurring payments from either balance are configured in the Balance payment provider."
  )}
>
  <AdminButton
    size="sm"
    variant="ghost"
    onclick={() =>
      onOpenSettingsPath(destination === "partner" ? ["partner"] : ["payments", "balance"])}
  >
    {destination === "partner"
      ? at("settings_balance_open_partner", {}, "Partner settings")
      : at("settings_partner_open_balance", {}, "Balance provider")}
    <ArrowRight size={14} />
  </AdminButton>
</AdminSettingCard>
