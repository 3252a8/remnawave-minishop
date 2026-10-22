<script lang="ts">
  import * as Card from "$components/ui/card/index.js";
  import {
    AdminBadge,
    AdminButton,
    AdminSubscriptionPlan,
    AdminChartEmptyState,
  } from "$components/patterns/admin/index.js";
  import type { TranslateFn } from "$components/patterns/admin/types";
  import {
    subscriptionPlanFilter,
    subscriptionPlanLabel,
    type ActiveTariff,
  } from "$lib/admin/subscriptionPlans";
  import type { UsersTariffFilter } from "$lib/admin/usersRouteFilters";

  let {
    at,
    rows,
    currentLang = "en",
    onOpenTariff,
  }: {
    at: TranslateFn;
    rows: ActiveTariff[];
    currentLang?: string;
    onOpenTariff: (filter: UsersTariffFilter) => void;
  } = $props();

  const visibleLimit = 6;
  let expanded = $state(false);
  const total = $derived(rows.reduce((sum, row) => sum + row.active_users, 0));
  const sorted = $derived(
    [...rows].sort(
      (a, b) =>
        b.active_users - a.active_users ||
        subscriptionPlanLabel(a, currentLang, at).localeCompare(
          subscriptionPlanLabel(b, currentLang, at),
          currentLang
        )
    )
  );
  const collapsible = $derived(sorted.length > visibleLimit);
  const visible = $derived(expanded ? sorted : sorted.slice(0, visibleLimit));
  const hiddenCount = $derived(sorted.length - visible.length);

  function percent(count: number): string {
    return new Intl.NumberFormat(currentLang, {
      style: "percent",
      maximumFractionDigits: 1,
    }).format(total ? count / total : 0);
  }
</script>

<Card.Root class="admin-stats-tariffs">
  <Card.Header class="admin-cn-card-header--lead">
    <Card.Title class="admin-cn-card-title--section"
      >{at("stats_tariffs_title", {}, "Active subscriptions by tariff")}</Card.Title
    >
    <Card.Description
      >{at(
        "stats_tariffs_hint",
        {},
        "Each user is counted once. Select a tariff to open its active users."
      )}</Card.Description
    >
    <Card.Action><AdminBadge>{total}</AdminBadge></Card.Action>
  </Card.Header>
  <Card.Content class="admin-tariff-distribution-content">
    {#if total > 0}
      <div
        class="admin-tariff-distribution"
        aria-label={at("stats_tariffs_title", {}, "Active subscriptions by tariff")}
      >
        {#each visible as row (subscriptionPlanFilter(row))}
          {@const filter = subscriptionPlanFilter(row)}
          <button
            type="button"
            class="admin-tariff-distribution-row"
            data-admin-tariff-filter={filter}
            aria-label={at(
              "stats_tariffs_open",
              { label: subscriptionPlanLabel(row, currentLang, at), count: row.active_users },
              "Show active users: {label}, {count}"
            )}
            onclick={() => onOpenTariff(filter)}
          >
            <AdminSubscriptionPlan
              plan={{ ...row, is_active: true }}
              {at}
              {currentLang}
              showActivity={false}
              showKey={rows.some(
                (other) =>
                  other.tariff_key !== row.tariff_key &&
                  subscriptionPlanLabel(other, currentLang, at) ===
                    subscriptionPlanLabel(row, currentLang, at)
              )}
            />
            <span class="admin-tariff-distribution-number"
              ><strong>{row.active_users}</strong><span>{percent(row.active_users)}</span></span
            >
            <span class="admin-tariff-distribution-track" aria-hidden="true"
              ><span style:width={`${total ? (row.active_users / total) * 100 : 0}%`}></span></span
            >
          </button>
        {/each}
      </div>
    {:else}
      <AdminChartEmptyState
        label={at("stats_tariffs_empty", {}, "No active subscriptions")}
        plotHeight={48}
      />
    {/if}
    {#if total > 0 && collapsible}
      <AdminButton
        variant="ghost"
        class="admin-tariff-distribution-toggle"
        aria-expanded={expanded}
        onclick={() => (expanded = !expanded)}
      >
        {expanded
          ? at("stats_tariffs_collapse", {}, "Show fewer")
          : at("stats_tariffs_show_all", { count: hiddenCount }, "Show all (+{count})")}
      </AdminButton>
    {/if}
  </Card.Content>
</Card.Root>

<style>
  :global(.admin-tariff-distribution-content) {
    display: grid;
    gap: 8px;
    padding-block: 12px;
  }
  .admin-tariff-distribution {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 220px), 1fr));
    gap: 8px;
  }
  .admin-tariff-distribution-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: 6px 10px;
    min-width: 0;
    min-height: 52px;
    padding: 8px 10px;
    border: 1px solid var(--admin-border);
    border-radius: 10px;
    background: transparent;
    color: var(--admin-text);
    font: inherit;
    text-align: left;
    overflow-wrap: anywhere;
    cursor: pointer;
  }
  .admin-tariff-distribution-row:hover {
    background: var(--admin-surface-2);
    border-color: var(--admin-muted);
  }
  .admin-tariff-distribution-row:focus-visible {
    outline: 2px solid var(--admin-ring);
    outline-offset: 2px;
  }
  .admin-tariff-distribution-number {
    display: flex;
    align-items: baseline;
    gap: 8px;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .admin-tariff-distribution-number strong {
    font-size: 15px;
    font-weight: 700;
  }
  .admin-tariff-distribution-number > span {
    min-width: 4ch;
    color: var(--admin-muted);
    font-size: 11px;
    text-align: right;
  }
  .admin-tariff-distribution-track {
    grid-column: 1 / -1;
    height: 3px;
    overflow: hidden;
    border-radius: 999px;
    background: color-mix(in srgb, var(--admin-muted) 15%, transparent);
  }
  .admin-tariff-distribution-track > span {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: var(--accent);
  }
  :global(.admin-tariff-distribution-toggle) {
    justify-self: start;
  }
</style>
