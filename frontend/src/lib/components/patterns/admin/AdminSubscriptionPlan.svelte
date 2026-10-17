<script lang="ts">
  import { subscriptionPlanLabel, type SubscriptionPlan } from "$lib/admin/subscriptionPlans";
  import AdminBadge from "./AdminBadge.svelte";
  import type { TranslateFn } from "./types";

  let {
    plan,
    at,
    currentLang = "en",
    showActivity = true,
    showKey = false,
  }: {
    plan?: SubscriptionPlan | null;
    at: TranslateFn;
    currentLang?: string;
    showActivity?: boolean;
    showKey?: boolean;
  } = $props();

  const label = $derived(subscriptionPlanLabel(plan, currentLang, at));
  const catalogStatus = $derived(
    plan?.kind === "tariff"
      ? !plan.is_configured
        ? at("users_tariff_deleted", {}, "Removed")
        : plan.is_enabled === false
          ? at("users_tariff_disabled", {}, "Disabled")
          : ""
      : ""
  );
</script>

<div class="admin-subscription-plan" class:is-empty={!plan}>
  <span class="admin-subscription-plan-name" title={plan?.tariff_key || label}>
    {#if plan?.kind === "trial" || plan?.kind === "unassigned"}
      <AdminBadge variant="warning" wrap>{label}</AdminBadge>
    {:else}
      {label}
    {/if}
  </span>
  {#if catalogStatus || (plan && !plan.is_active && showActivity) || (showKey && plan?.tariff_key && plan.tariff_key !== label)}
    <span class="admin-subscription-plan-meta">
      {#if showKey && plan?.tariff_key && plan.tariff_key !== label}<span>{plan.tariff_key}</span
        >{/if}
      {#if catalogStatus}<span>{catalogStatus}</span>{/if}
      {#if plan && !plan.is_active && showActivity}<span
          >{at("users_tariff_inactive", {}, "Inactive")}</span
        >{/if}
    </span>
  {/if}
</div>

<style>
  .admin-subscription-plan {
    display: grid;
    min-width: 0;
    gap: 4px;
  }
  .admin-subscription-plan-name {
    color: var(--admin-text);
    font-size: 12px;
    font-weight: 650;
    overflow-wrap: anywhere;
  }
  .is-empty .admin-subscription-plan-name {
    color: var(--admin-muted);
    font-weight: 450;
  }
  .admin-subscription-plan-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 3px 8px;
    color: var(--admin-muted);
    font-size: 10px;
    font-weight: 450;
  }
</style>
