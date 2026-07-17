<script lang="ts">
  import { getPaymentsStore, getStatsStore } from "$lib/admin/context";
  import { FileText, TrendingDown, TrendingUp, User } from "$components/ui/icons.js";
  import { onMount, type ComponentType, type SvelteComponent } from "svelte";

  import Badge from "$components/ui/badge.svelte";
  import * as Card from "$components/ui/card/index.js";
  import {
    AdminDashboardGrid,
    AdminDashboardStack,
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminRevenueCustomRangePopover,
    AdminSectionHeader,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
  import StatsPanelDashboard from "./stats/StatsPanelDashboard.svelte";
  import StatsSkeleton from "./stats/StatsSkeleton.svelte";
  import StatsSyncStrip from "./stats/StatsSyncStrip.svelte";
  import {
    aggregateRevenueSeries,
    filterDailyByIsoRange,
    inclusiveDaySpan,
    sliceLastDays,
  } from "../../lib/admin/revenueSeriesAgg.js";
  import {
    computeRevenueKpis,
    formatTrafficGbCell,
    growthBadgeVariant,
    parsePanelBandwidth,
    parsePanelNodeTraffic,
    parsePanelSystem,
    paymentDescriptionDisplay,
    type AdminStats,
    type CustomRangeApply,
    type PanelNodeTraffic,
    type PanelStats,
    type PanelSystemMetrics,
    type RevenueKpis,
    type RevenuePoint,
  } from "$lib/admin/statsDerivations";
  import type { PaymentOut } from "$lib/admin/stores/paymentsStore";
  import type { StatsState } from "$lib/admin/stores/statsStore";
  import type { UsersFilter } from "$lib/admin/usersRouteFilters";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type FormatterFn = (value: unknown, currency?: string) => string;
  type DateFormatterFn = (value: unknown) => string;
  type AdminBadgeVariant = "success" | "danger" | "warning" | "muted";
  type RevenueGranularity = "day" | "week" | "month";
  type RevenueRangeMode = "preset" | "custom";
  type IsoRange = { from: string; to: string };
  type DynamicComponent = ComponentType<SvelteComponent<Record<string, unknown>>>;

  let {
    at,
    fmtDate = (value) => String(value ?? ""),
    fmtDateShort = (value) => String(value ?? ""),
    fmtMoney = (value) => String(value ?? ""),
    paymentStatusVariant = () => "muted",
    onOpenUserCard = () => {},
    onOpenUsersFilter = () => {},
  }: {
    at: TranslateFn;
    fmtDate?: DateFormatterFn;
    fmtDateShort?: DateFormatterFn;
    fmtMoney?: FormatterFn;
    paymentStatusVariant?: (status: unknown) => AdminBadgeVariant;
    onOpenUserCard?: (userId: unknown) => void;
    onOpenUsersFilter?: (filter: UsersFilter) => void;
  } = $props();

  const paymentsStore = getPaymentsStore();
  const statsStore = getStatsStore();

  const statsState = $derived(statsStore);
  const rawStats: StatsState["stats"] = $derived(statsState.stats);
  const stats: AdminStats | null = $derived(rawStats as AdminStats | null);
  const statsError = $derived(statsState.statsError || "");
  const statsLoading = $derived(Boolean(statsState.statsLoading));
  const showSkeleton = $derived(!stats && !statsError);
  const currency = $derived(stats?.currency_symbol || "RUB");
  const fin: AdminStats["financial"] = $derived(stats?.financial || {});
  const users: AdminStats["users"] = $derived(stats?.users || {});
  const panelPayload: PanelStats | null = $derived(stats?.panel ?? null);
  const panelMetrics: PanelSystemMetrics | null = $derived(
    panelPayload && !panelPayload.error ? parsePanelSystem(panelPayload) : null
  );
  const panelBw: { week: unknown; month: unknown } | null = $derived(
    panelPayload && !panelPayload.error ? parsePanelBandwidth(panelPayload) : null
  );
  const panelNodeTraffic: PanelNodeTraffic | null = $derived(
    panelPayload && !panelPayload.error ? parsePanelNodeTraffic(panelPayload) : null
  );

  /** Same rows as the «Per node (7 days)» block — not system.nodes.totalOnline from /system/stats */
  const panelNodesListedCount = $derived(panelNodeTraffic?.seven?.length ?? 0);

  const REVENUE_CHART_MAX_CSS_HEIGHT = 204;

  const REVENUE_PRESET_DAYS = [7, 14, 30, 90, 180, 365];

  let revenueRangeMode = $state<RevenueRangeMode>("preset");
  let revenuePresetDays = $state(14);
  let revenueCustomIso = $state<IsoRange | null>(null);
  let revenueGranularity = $state<RevenueGranularity>("day");
  let revenueCustomPopoverOpen = $state(false);
  let AdminRevenueChartComponent = $state<DynamicComponent | null>(null);

  const dailySeries: RevenuePoint[] = $derived(
    Array.isArray(fin.daily_series) ? fin.daily_series : []
  );
  const revenueBoundsIso: { min: string; max: string } | null = $derived(
    dailySeries.length > 0
      ? { min: dailySeries[0].date, max: dailySeries[dailySeries.length - 1].date }
      : null
  );

  const revenueDailyFiltered: RevenuePoint[] = $derived.by(() => {
    if (!dailySeries.length) return [];
    if (revenueRangeMode === "custom" && revenueCustomIso) {
      return filterDailyByIsoRange(dailySeries, revenueCustomIso.from, revenueCustomIso.to);
    }
    return sliceLastDays(dailySeries, revenuePresetDays);
  });

  const revenueChartSeries: RevenuePoint[] = $derived(
    aggregateRevenueSeries(revenueDailyFiltered, revenueGranularity)
  );

  const revenueKpis: RevenueKpis = $derived(computeRevenueKpis(fin, dailySeries));
  const chartRangeSum = $derived(
    revenueChartSeries.reduce((a, p) => a + (Number(p.amount) || 0), 0)
  );

  function loadRevenueChart(): void {
    if (AdminRevenueChartComponent) return;
    void import("$components/patterns/admin/AdminRevenueChart.svelte").then((module) => {
      AdminRevenueChartComponent = module.default as unknown as DynamicComponent;
    });
  }

  $effect(() => {
    if (revenueChartSeries.length) loadRevenueChart();
  });

  function setRevenuePresetDays(days: number): void {
    const next = Number(days);
    if (!REVENUE_PRESET_DAYS.includes(next)) return;
    revenueRangeMode = "preset";
    revenuePresetDays = next;
    revenueCustomPopoverOpen = false;
  }

  function onCustomRangeApply({ fromIso, toIso }: CustomRangeApply): void {
    revenueRangeMode = "custom";
    revenueCustomIso = { from: fromIso, to: toIso };
  }

  function setRevenueGranularity(next: unknown): void {
    const g = String(next);
    if (g !== "day" && g !== "week" && g !== "month") return;
    revenueGranularity = g;
  }

  function revenuePeriodLabel(days: number): string {
    return at(`stats_revenue_period_${days}`, {}, `${days}d`);
  }

  function revenueChartHintKey(): string {
    if (revenueGranularity === "week") return "stats_revenue_chart_hint_week";
    if (revenueGranularity === "month") return "stats_revenue_chart_hint_month";
    return "stats_revenue_chart_hint";
  }

  const revenueChartShortfall = $derived(
    revenueRangeMode === "preset" && dailySeries.length < revenuePresetDays
  );
  const revenueCustomDaySpan = $derived(
    revenueRangeMode === "custom" && revenueCustomIso
      ? inclusiveDaySpan(revenueCustomIso.from, revenueCustomIso.to)
      : 0
  );
  const recentPaymentHeaders = $derived([
    at("id", {}, "ID"),
    at("user", {}, "User"),
    at("payments_col_user_id", {}, "ID"),
    at("payments_col_traffic_regular", {}, "Main traffic"),
    at("payments_col_traffic_premium", {}, "Premium traffic"),
    at("amount", {}, "Amount"),
    at("provider", {}, "Provider"),
    at("description", {}, "Description"),
    at("status", {}, "Status"),
    at("date", {}, "Date"),
  ]);
  const recentPayments: PaymentOut[] = $derived((stats?.recent_payments || []).slice(0, 10));

  function userFilterActionLabel(label: string): string {
    return at("stats_open_user_filter", { label }, `Show users: ${label}`);
  }

  onMount(() => {
    void statsStore.loadStats();
  });
</script>

{#if statsError}
  <AdminEmptyState>{at("stats_error", { error: statsError }, "")}</AdminEmptyState>
{:else if showSkeleton}
  <StatsSkeleton {at} headers={recentPaymentHeaders} />
{:else if stats}
  <AdminDashboardStack>
    <AdminSectionHeader
      title={at("stats_section_audience", {}, "")}
      description={at("stats_section_audience_hint", {}, "")}
    />

    <AdminDashboardGrid columns={3}>
      <Card.Root>
        <Card.Header>
          <Card.Description>{at("stats_label_users", {}, "")}</Card.Description>
          <Card.Title>
            <button
              type="button"
              class="admin-stats-user-filter admin-stats-user-filter--count"
              data-admin-user-filter="all"
              aria-label={userFilterActionLabel(at("filter_all", {}, "All"))}
              onclick={() => onOpenUsersFilter("all")}>{users.total_users ?? 0}</button
            >
          </Card.Title>
          <Card.Action>
            <button
              type="button"
              class="admin-stats-user-filter admin-stats-user-filter--badge"
              data-admin-user-filter="active_today"
              aria-label={userFilterActionLabel(at("filter_active_today", {}, "Registered today"))}
              onclick={() => onOpenUsersFilter("active_today")}
              ><Badge variant="outline">+{users.active_today ?? 0}</Badge></button
            >
          </Card.Action>
        </Card.Header>
        <Card.Footer class="admin-cn-card-footer--stack">
          <div class="admin-cn-card-footer-primary">
            <button
              type="button"
              class="admin-stats-user-filter"
              data-admin-user-filter="banned"
              aria-label={userFilterActionLabel(at("filter_banned", {}, "Banned"))}
              onclick={() => onOpenUsersFilter("banned")}
              >{at("stats_trend_banned", { count: users.banned_users ?? 0 }, "")}</button
            >
          </div>
          <div class="admin-cn-card-footer-muted">
            <button
              type="button"
              class="admin-stats-user-filter"
              data-admin-user-filter="referred"
              aria-label={userFilterActionLabel(at("filter_referred", {}, "Referred users"))}
              onclick={() => onOpenUsersFilter("referred")}
              >{at("stats_trend_referrals", { count: users.referral_users ?? 0 }, "")}</button
            >
          </div>
        </Card.Footer>
      </Card.Root>

      <Card.Root>
        <Card.Header>
          <Card.Description>{at("stats_label_active_subs", {}, "")}</Card.Description>
          <Card.Title>
            <button
              type="button"
              class="admin-stats-user-filter admin-stats-user-filter--count"
              data-admin-user-filter="active_subscription"
              aria-label={userFilterActionLabel(
                at("filter_active_subscription", {}, "With active subscription")
              )}
              onclick={() => onOpenUsersFilter("active_subscription")}
              >{users.active_subscriptions ?? 0}</button
            >
          </Card.Title>
          <Card.Action>
            <Badge variant="outline"
              >{users.total_users
                ? Math.round(((users.active_subscriptions ?? 0) / (users.total_users || 1)) * 100)
                : 0}%</Badge
            >
          </Card.Action>
        </Card.Header>
        <Card.Footer class="admin-cn-card-footer--stack">
          <div class="admin-cn-card-footer-primary">
            <button
              type="button"
              class="admin-stats-user-filter"
              data-admin-user-filter="paid"
              aria-label={userFilterActionLabel(at("stats_label_paid_subs", {}, "Paid users"))}
              onclick={() => onOpenUsersFilter("paid")}
              >{at("stats_trend_paid", { count: users.paid_subscriptions ?? 0 }, "")}</button
            >
            <span aria-hidden="true">·</span>
            <button
              type="button"
              class="admin-stats-user-filter"
              data-admin-user-filter="free"
              aria-label={userFilterActionLabel(at("stats_label_free_users", {}, "Free users"))}
              onclick={() => onOpenUsersFilter("free")}
              >{at("stats_trend_free", { count: users.free_subscription_users ?? 0 }, "")}</button
            >
            <span aria-hidden="true">·</span>
            <button
              type="button"
              class="admin-stats-user-filter"
              data-admin-user-filter="trial"
              aria-label={userFilterActionLabel(at("stats_label_trial_users", {}, "Trial users"))}
              onclick={() => onOpenUsersFilter("trial")}
              >{at("stats_trend_trials", { count: users.trial_users ?? 0 }, "")}</button
            >
          </div>
          <div class="admin-cn-card-footer-muted">
            {at("stats_card_active_subs_caption", {}, "")}
          </div>
        </Card.Footer>
      </Card.Root>

      <Card.Root>
        <Card.Header>
          <Card.Description>{at("stats_label_inactive", {}, "")}</Card.Description>
          <Card.Title>
            <button
              type="button"
              class="admin-stats-user-filter admin-stats-user-filter--count"
              data-admin-user-filter="inactive_subscription"
              aria-label={userFilterActionLabel(
                at("filter_inactive_subscription", {}, "Without active subscription")
              )}
              onclick={() => onOpenUsersFilter("inactive_subscription")}
              >{users.inactive_users ?? 0}</button
            >
          </Card.Title>
          <Card.Action>
            <Badge variant="outline"
              >{users.total_users
                ? Math.round(((users.inactive_users ?? 0) / (users.total_users || 1)) * 100)
                : 0}%</Badge
            >
          </Card.Action>
        </Card.Header>
        <Card.Footer class="admin-cn-card-footer--stack">
          <div class="admin-cn-card-footer-primary">
            <button
              type="button"
              class="admin-stats-user-filter"
              data-admin-user-filter="expired_subscription"
              aria-label={userFilterActionLabel(
                at("filter_expired_subscription", {}, "With expired subscription")
              )}
              onclick={() => onOpenUsersFilter("expired_subscription")}
              >{at(
                "stats_trend_expired_subscriptions",
                { count: users.expired_subscription_users ?? 0 },
                ""
              )}</button
            >
          </div>
          <div class="admin-cn-card-footer-muted">{at("stats_card_inactive_caption", {}, "")}</div>
        </Card.Footer>
      </Card.Root>
    </AdminDashboardGrid>

    <AdminSectionHeader
      title={at("stats_section_revenue", {}, "")}
      description={at("stats_section_revenue_hint", {}, "")}
    />

    <Card.Root>
      <Card.Header>
        <Card.Description>{at("stats_label_today_rev", {}, "")}</Card.Description>
        <Card.Title>{fmtMoney(fin.today_revenue, currency)}</Card.Title>
        <Card.Action>
          {#if revenueKpis.growthPct != null}
            <Badge variant={growthBadgeVariant(revenueKpis.growthPct)}>
              {#if revenueKpis.growthPct >= 0}
                <TrendingUp />
              {:else}
                <TrendingDown />
              {/if}
              {revenueKpis.growthPct >= 0 ? "+" : ""}{revenueKpis.growthPct.toFixed(1)}%
            </Badge>
          {:else}
            <Badge variant="outline">—</Badge>
          {/if}
        </Card.Action>
      </Card.Header>
      <Card.Content>
        <div class="admin-revenue-kpis">
          <div class="admin-revenue-kpi">
            <div class="admin-revenue-kpi-label">
              {at("stats_trend_payments", { count: fin.today_payments_count ?? 0 }, "")}
            </div>
            <div class="admin-revenue-kpi-value">{fin.today_payments_count ?? 0}</div>
          </div>
          <div class="admin-revenue-kpi">
            <div class="admin-revenue-kpi-label">
              {at("stats_revenue_avg_ticket_label", {}, "")}
            </div>
            <div class="admin-revenue-kpi-value">
              {revenueKpis.avgToday != null ? fmtMoney(revenueKpis.avgToday, currency) : "—"}
            </div>
            {#if revenueKpis.avgToday == null}
              <div class="admin-revenue-kpi-sub">{at("stats_revenue_avg_none", {}, "")}</div>
            {/if}
          </div>
          <div class="admin-revenue-kpi">
            <div class="admin-revenue-kpi-label">{at("stats_revenue_rolling_week", {}, "")}</div>
            <div class="admin-revenue-kpi-value">{fmtMoney(fin.week_revenue, currency)}</div>
          </div>
          <div class="admin-revenue-kpi">
            <div class="admin-revenue-kpi-label">{at("stats_revenue_rolling_month", {}, "")}</div>
            <div class="admin-revenue-kpi-value">{fmtMoney(fin.month_revenue, currency)}</div>
          </div>
          <div class="admin-revenue-kpi">
            <div class="admin-revenue-kpi-label">{at("stats_revenue_last_7_calendar", {}, "")}</div>
            <div class="admin-revenue-kpi-value">{fmtMoney(revenueKpis.last7, currency)}</div>
          </div>
          <div class="admin-revenue-kpi">
            <div class="admin-revenue-kpi-label">{at("stats_label_all_time", {}, "")}</div>
            <div class="admin-revenue-kpi-value">{fmtMoney(fin.all_time_revenue, currency)}</div>
          </div>
          <div class="admin-revenue-kpi admin-revenue-kpi--wide">
            <div class="admin-revenue-kpi-label">{at("stats_revenue_total_14", {}, "")}</div>
            <div class="admin-revenue-kpi-value">{fmtMoney(revenueKpis.total14, currency)}</div>
            <div class="admin-revenue-kpi-sub">
              {#if revenueKpis.growthPct != null}
                <span
                  class="admin-revenue-kpi-growth"
                  class:is-up={revenueKpis.growthPct >= 0}
                  class:is-down={revenueKpis.growthPct < 0}
                >
                  {at("stats_revenue_growth", { value: revenueKpis.growthPct.toFixed(1) }, "")}
                </span>
              {:else}
                {at("stats_revenue_growth_na", {}, "")}
              {/if}
            </div>
          </div>
        </div>

        <div class="admin-revenue-chart">
          <div class="admin-revenue-chart-head">
            <div class="admin-revenue-chart-title">{at("stats_revenue_chart_title", {}, "")}</div>
            <div class="admin-revenue-chart-toolbar">
              <div
                class="admin-revenue-period"
                role="tablist"
                aria-label={at("stats_revenue_chart_aria", {}, "")}
              >
                {#each REVENUE_PRESET_DAYS as d (d)}
                  <button
                    type="button"
                    class="admin-revenue-period-btn"
                    class:is-active={revenueRangeMode === "preset" && revenuePresetDays === d}
                    role="tab"
                    aria-selected={revenueRangeMode === "preset" && revenuePresetDays === d}
                    onclick={() => setRevenuePresetDays(d)}
                  >
                    {revenuePeriodLabel(d)}
                  </button>
                {/each}
              </div>
              <AdminRevenueCustomRangePopover
                bind:open={revenueCustomPopoverOpen}
                minIso={revenueBoundsIso?.min ?? ""}
                maxIso={revenueBoundsIso?.max ?? ""}
                committedFrom={revenueCustomIso?.from ?? ""}
                committedTo={revenueCustomIso?.to ?? ""}
                title={at("stats_revenue_custom_range_title", {}, "")}
                triggerLabel={at("stats_revenue_period_custom", {}, "Custom")}
                applyLabel={at("stats_revenue_custom_range_apply", {}, "Apply")}
                isActive={revenueRangeMode === "custom"}
                onApply={onCustomRangeApply}
              />
            </div>
          </div>
          <div
            class="admin-revenue-granularity"
            role="tablist"
            aria-label={at("stats_revenue_granularity_aria", {}, "")}
          >
            {#each ["day", "week", "month"] as g (g)}
              <button
                type="button"
                class="admin-revenue-period-btn admin-revenue-period-btn--compact"
                class:is-active={revenueGranularity === g}
                role="tab"
                aria-selected={revenueGranularity === g}
                onclick={() => setRevenueGranularity(g)}
              >
                {at(`stats_revenue_granularity_${g}`, {}, g)}
              </button>
            {/each}
          </div>
          <p class="admin-revenue-chart-hint admin-muted">{at(revenueChartHintKey(), {}, "")}</p>
          {#if revenueChartSeries.length}
            <div class="admin-revenue-chart-meta admin-muted">
              <span
                >{at(
                  "stats_revenue_chart_range_sum",
                  { value: fmtMoney(chartRangeSum, currency) },
                  ""
                )}</span
              >
              {#if revenueGranularity !== "day"}
                <span class="admin-revenue-chart-meta-sep" aria-hidden="true">·</span>
                <span
                  >{at(
                    "stats_revenue_chart_bucket_count",
                    { count: revenueChartSeries.length },
                    ""
                  )}</span
                >
              {/if}
              {#if revenueChartShortfall}
                <span class="admin-revenue-chart-meta-sep" aria-hidden="true">·</span>
                <span
                  >{at(
                    "stats_revenue_chart_days_available",
                    { count: dailySeries.length },
                    ""
                  )}</span
                >
              {:else if revenueRangeMode === "custom" && revenueCustomDaySpan > 0}
                <span class="admin-revenue-chart-meta-sep" aria-hidden="true">·</span>
                <span
                  >{at("stats_revenue_chart_custom_span", { days: revenueCustomDaySpan }, "")}</span
                >
              {/if}
            </div>
            <div class="admin-revenue-svg-frame admin-revenue-svg-frame--chart">
              {#if AdminRevenueChartComponent}
                <AdminRevenueChartComponent
                  series={revenueChartSeries}
                  plotHeight={REVENUE_CHART_MAX_CSS_HEIGHT}
                  {fmtMoney}
                  {currency}
                  legendTimeLabel={at("stats_revenue_chart_uplot_time", {}, "Time")}
                  legendValueLabel={at("stats_revenue_chart_uplot_value", {}, "Value")}
                />
              {:else}
                <span
                  class="admin-skeleton admin-revenue-chart-skeleton"
                  style={`height:${REVENUE_CHART_MAX_CSS_HEIGHT}px`}
                ></span>
              {/if}
            </div>
          {:else}
            <p class="admin-muted">{at("stats_revenue_no_chart", {}, "")}</p>
          {/if}
        </div>
      </Card.Content>
    </Card.Root>

    <StatsPanelDashboard
      {at}
      {panelPayload}
      {panelMetrics}
      {panelBw}
      {panelNodeTraffic}
      {panelNodesListedCount}
    />

    <StatsSyncStrip {at} {stats} {fmtDateShort} />

    <Card.Root>
      <Card.Header class="admin-cn-card-header--lead">
        <Card.Title class="admin-cn-card-title--section"
          >{at("stats_recent_payments", {}, "")}</Card.Title
        >
      </Card.Header>
      <Card.Content class="admin-cn-card-content--flush">
        <div class="admin-table-wrap">
          {#if statsLoading}
            <AdminTableSkeleton
              headers={recentPaymentHeaders}
              rows={5}
              widths={[
                "48px",
                "148px",
                "88px",
                "72px",
                "72px",
                "78px",
                "82px",
                "140px",
                "72px",
                "96px",
              ]}
            />
          {:else if recentPayments.length}
            <AdminTable>
              <thead>
                <tr>
                  <th>{at("id", {}, "ID")}</th>
                  <th>{at("user", {}, "User")}</th>
                  <th>{at("payments_col_user_id", {}, "ID")}</th>
                  <th>{at("payments_col_traffic_regular", {}, "Main traffic")}</th>
                  <th>{at("payments_col_traffic_premium", {}, "Premium traffic")}</th>
                  <th>{at("amount", {}, "Amount")}</th>
                  <th>{at("provider", {}, "Provider")}</th>
                  <th>{at("description", {}, "Description")}</th>
                  <th>{at("status", {}, "Status")}</th>
                  <th>{at("date", {}, "Date")}</th>
                </tr>
              </thead>
              <tbody>
                {#each recentPayments as p (p.payment_id)}
                  <tr>
                    <td class="admin-cell-id" data-label="ID">
                      <AdminButton
                        class="admin-payment-id-btn"
                        variant="ghost"
                        size="sm"
                        title={at("payment_detail_open", {}, "Open payment")}
                        aria-label={at("payment_detail_open", {}, "Open payment")}
                        onclick={() => paymentsStore.openPayment(p)}
                      >
                        <FileText size={14} />
                        #{p.payment_id}
                      </AdminButton>
                    </td>
                    <td class="admin-cell-user-with-action" data-label={at("user", {}, "User")}>
                      <span class="admin-payments-user-cell">
                        <AdminButton
                          class="admin-payments-user-btn"
                          variant="ghost"
                          size="icon"
                          title={at("payments_open_user", {}, "Open user card")}
                          aria-label={at("payments_open_user", {}, "Open user card")}
                          onclick={() => onOpenUserCard(p.user_id)}
                        >
                          <User size={14} />
                        </AdminButton>
                        <span class="admin-payments-user-name">{p.user_label || p.user_id}</span>
                      </span>
                    </td>
                    <td class="admin-cell-mono" data-label={at("payments_col_user_id", {}, "ID")}>
                      {p.user_id != null ? p.user_id : "—"}
                    </td>
                    <td
                      class="admin-cell-traffic-gb"
                      data-label={at("payments_col_traffic_regular", {}, "Main traffic")}
                    >
                      {formatTrafficGbCell(p.traffic_regular_gb)}
                    </td>
                    <td
                      class="admin-cell-traffic-gb"
                      data-label={at("payments_col_traffic_premium", {}, "Premium traffic")}
                    >
                      {formatTrafficGbCell(p.traffic_premium_gb)}
                    </td>
                    <td data-label={at("amount", {}, "Amount")}>
                      {fmtMoney(p.amount, p.currency ?? undefined)}
                    </td>
                    <td data-label={at("provider", {}, "Provider")}>{p.provider}</td>
                    <td class="admin-cell-wrap" data-label={at("description", {}, "Description")}
                      >{paymentDescriptionDisplay(p, at)}</td
                    >
                    <td data-label={at("status", {}, "Status")}>
                      <AdminBadge variant={paymentStatusVariant(p.status)}>{p.status}</AdminBadge>
                    </td>
                    <td data-label={at("date", {}, "Date")}>{fmtDate(p.created_at)}</td>
                  </tr>
                {/each}
              </tbody>
            </AdminTable>
          {:else}
            <AdminEmptyState tone="card"
              ><span class="admin-muted">{at("no_data", {}, "")}</span></AdminEmptyState
            >
          {/if}
        </div>
      </Card.Content>
    </Card.Root>
  </AdminDashboardStack>
{/if}

<style>
  .admin-stats-user-filter {
    appearance: none;
    border: 0;
    border-radius: 5px;
    padding: 0;
    background: transparent;
    color: inherit;
    font: inherit;
    line-height: inherit;
    text-align: inherit;
    cursor: pointer;
    text-decoration: underline;
    text-decoration-color: transparent;
    text-underline-offset: 3px;
    transition:
      color 140ms ease,
      text-decoration-color 140ms ease;
  }

  .admin-stats-user-filter:hover {
    color: var(--accent);
    text-decoration-color: currentColor;
  }

  .admin-stats-user-filter:focus-visible {
    outline: 2px solid var(--admin-ring);
    outline-offset: 3px;
  }

  .admin-stats-user-filter--count {
    display: inline-block;
  }

  .admin-stats-user-filter--badge {
    display: block;
    border-radius: 999px;
  }

  .admin-payments-user-cell {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  .admin-payments-user-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-cell-user-with-action :global(.admin-payments-user-btn.admin-btn) {
    width: 30px;
    height: 30px;
    min-width: 30px;
    min-height: 30px;
    flex-shrink: 0;
    padding: 0;
    border-radius: 7px;
  }

  .admin-cell-user-with-action :global(.admin-payments-user-btn svg) {
    width: 14px;
    height: 14px;
  }

  .admin-cell-id :global(.admin-payment-id-btn.admin-btn) {
    height: 28px;
    min-height: 28px;
    padding: 0 8px;
    gap: 6px;
    border-radius: 7px;
    color: var(--admin-text);
    font-family: var(--font-mono);
    font-size: 12px;
  }
</style>
