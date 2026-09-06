<script lang="ts">
  import { getStatsStore } from "$lib/admin/context";
  import { TrendingDown, TrendingUp } from "$components/ui/icons.js";
  import { onMount, type ComponentType, type SvelteComponent } from "svelte";

  import Badge from "$components/ui/badge.svelte";
  import * as Card from "$components/ui/card/index.js";
  import {
    AdminDashboardGrid,
    AdminDashboardStack,
    AdminChartEmptyState,
    AdminChartSkeleton,
    AdminEmptyState,
    AdminRevenueCustomRangePopover,
    AdminRevenueTabs,
  } from "$components/patterns/admin/index.js";
  import PaymentTable from "./PaymentTable.svelte";
  import StatsPanelDashboard from "./stats/StatsPanelDashboard.svelte";
  import StatsSkeleton from "./stats/StatsSkeleton.svelte";
  import StatsSyncStrip from "./stats/StatsSyncStrip.svelte";
  import {
    aggregateRevenueSeries,
    filterDailyByIsoRange,
    filterRevenueByPreset,
    hasChartValues,
    inclusiveDaySpan,
    isRevenueGranularity,
    isRevenuePreset,
    REVENUE_GRANULARITIES,
    REVENUE_PRESETS,
    type RevenueGranularity,
    type RevenuePreset,
  } from "../../lib/admin/revenueSeriesAgg.js";
  import {
    computeRevenueKpis,
    growthBadgeVariant,
    parsePanelBandwidth,
    parsePanelNodeTraffic,
    parsePanelSystem,
    type AdminStats,
    type CustomRangeApply,
    type PanelNodeTraffic,
    type PanelStats,
    type PanelSystemMetrics,
    type RevenueKpis,
    type RevenuePoint,
  } from "$lib/admin/statsDerivations";
  import { paymentDescriptionDisplay } from "$lib/admin/paymentTable.js";
  import type { PaymentOut } from "$lib/admin/stores/paymentsStore";
  import type { StatsState } from "$lib/admin/stores/statsStore";
  import type { UsersFilter } from "$lib/admin/usersRouteFilters";
  import { sortAdminRows, type AdminSortColumn } from "$lib/admin/tableSort.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type FormatterFn = (value: unknown, currency?: string | null) => string;
  type DateFormatterFn = (value: unknown) => string;
  type AdminBadgeVariant = "success" | "danger" | "warning" | "muted";
  type RevenueRangeMode = "preset" | "custom";
  type IsoRange = { from: string; to: string };
  type DynamicComponent = ComponentType<SvelteComponent<Record<string, unknown>>>;

  let {
    at,
    currentLang = "en",
    fmtDate = (value) => String(value ?? ""),
    fmtDateShort = (value) => String(value ?? ""),
    fmtMoney = (value) => String(value ?? ""),
    paymentStatusVariant = () => "muted",
    onOpenUserCard = () => {},
    onOpenUsersFilter = () => {},
  }: {
    at: TranslateFn;
    currentLang?: string;
    fmtDate?: DateFormatterFn;
    fmtDateShort?: DateFormatterFn;
    fmtMoney?: FormatterFn;
    paymentStatusVariant?: (status: unknown) => AdminBadgeVariant;
    onOpenUserCard?: (userId: unknown) => void;
    onOpenUsersFilter?: (filter: UsersFilter) => void;
  } = $props();

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

  const emptyRevenuePreview =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("stats_scenario") === "empty_revenue";

  let revenueRangeMode = $state<RevenueRangeMode>("preset");
  let revenuePreset = $state<RevenuePreset>(14);
  let revenueCustomIso = $state<IsoRange | null>(null);
  let revenueGranularity = $state<RevenueGranularity>("day");
  let revenueCustomPopoverOpen = $state(false);
  let AdminRevenueChartComponent = $state<DynamicComponent | null>(null);

  const dailySeries: RevenuePoint[] = $derived(
    Array.isArray(fin.daily_series)
      ? fin.daily_series.map((point) => (emptyRevenuePreview ? { ...point, amount: 0 } : point))
      : []
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
    return filterRevenueByPreset(dailySeries, revenuePreset, revenueBoundsIso?.max);
  });

  const revenueChartSeries: RevenuePoint[] = $derived(
    aggregateRevenueSeries(revenueDailyFiltered, revenueGranularity)
  );

  const revenueKpis: RevenueKpis = $derived(computeRevenueKpis(fin, dailySeries));
  const revenueHasValues = $derived(hasChartValues(revenueChartSeries));
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
    if (revenueHasValues) loadRevenueChart();
  });

  function setRevenuePreset(value: unknown): void {
    const next = value === "all" ? "all" : Number(value);
    if (!isRevenuePreset(next)) return;
    revenueRangeMode = "preset";
    revenuePreset = next;
    revenueCustomPopoverOpen = false;
  }

  function onCustomRangeApply({ fromIso, toIso }: CustomRangeApply): void {
    revenueRangeMode = "custom";
    revenueCustomIso = { from: fromIso, to: toIso };
  }

  function setRevenueGranularity(next: unknown): void {
    if (!isRevenueGranularity(next)) return;
    revenueGranularity = next;
  }

  function revenuePeriodLabel(preset: RevenuePreset): string {
    return at(`stats_revenue_period_${preset}`, {}, preset === "all" ? "All time" : `${preset}d`);
  }

  function revenueChartHintKey(): string {
    if (revenueGranularity === "week") return "stats_revenue_chart_hint_week";
    if (revenueGranularity === "month") return "stats_revenue_chart_hint_month";
    if (revenueGranularity === "year") return "stats_revenue_chart_hint_year";
    return "stats_revenue_chart_hint";
  }

  const revenueChartShortfall = $derived(
    revenueRangeMode === "preset" && revenuePreset !== "all" && dailySeries.length < revenuePreset
  );
  const revenueCustomDaySpan = $derived(
    revenueRangeMode === "custom" && revenueCustomIso
      ? inclusiveDaySpan(revenueCustomIso.from, revenueCustomIso.to)
      : 0
  );
  const recentPaymentHeaders = $derived([
    at("id", {}, "ID"),
    at("user", {}, "User"),
    at("payments_col_purchases", {}, "Add-ons"),
    at("amount", {}, "Amount"),
    at("payments_col_discount", {}, "Discount"),
    at("provider", {}, "Provider"),
    at("description", {}, "Description"),
    at("status", {}, "Status"),
    at("date", {}, "Date"),
  ]);
  let recentPaymentsSort = $state("date_desc");
  const recentPaymentSortColumns = [
    { asc: "id_asc", desc: "id_desc", defaultDirection: "desc", value: (row) => row.payment_id },
    { asc: "user_asc", desc: "user_desc", defaultDirection: "asc", value: (row) => row.user_label },
    {
      asc: "amount_asc",
      desc: "amount_desc",
      defaultDirection: "desc",
      value: (row) => row.amount,
    },
    {
      asc: "discount_asc",
      desc: "discount_desc",
      defaultDirection: "desc",
      value: (row) =>
        Number(row.checkout_discount_amount || 0) || Number(row.promo_discount_percent || 0),
    },
    {
      asc: "provider_asc",
      desc: "provider_desc",
      defaultDirection: "asc",
      value: (row) => row.provider,
    },
    {
      asc: "description_asc",
      desc: "description_desc",
      defaultDirection: "asc",
      value: (row) => paymentDescriptionDisplay(row, at),
    },
    { asc: "status_asc", desc: "status_desc", defaultDirection: "asc", value: (row) => row.status },
    {
      asc: "date_asc",
      desc: "date_desc",
      defaultDirection: "desc",
      value: (row) => row.created_at,
    },
  ] satisfies AdminSortColumn<PaymentOut>[];
  const recentPayments: PaymentOut[] = $derived(
    sortAdminRows(
      (stats?.recent_payments || [])
        .filter((payment) => payment.status === "succeeded")
        .slice(0, 10),
      recentPaymentsSort,
      recentPaymentSortColumns
    )
  );

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
    <AdminDashboardGrid columns={3}>
      <Card.Root class="admin-stats-audience-card">
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

      <Card.Root class="admin-stats-audience-card">
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

      <Card.Root class="admin-stats-audience-card">
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
            <div class="admin-revenue-kpi-label">{at("gifts_free_stats")}</div>
            <div class="admin-revenue-kpi-value">{fin.admin_gifts_count ?? 0}</div>
            <div class="admin-revenue-kpi-label">
              {at("gifts_free_stats_hint", { count: fin.admin_gifts_activated_count ?? 0 })}
            </div>
          </div>
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
              <AdminRevenueTabs
                value={revenueRangeMode === "preset" ? String(revenuePreset) : ""}
                items={REVENUE_PRESETS.map((preset) => ({
                  value: String(preset),
                  label: revenuePeriodLabel(preset),
                }))}
                ariaLabel={at("stats_revenue_chart_aria", {}, "")}
                onValueChange={setRevenuePreset}
              />
              <AdminRevenueCustomRangePopover
                bind:open={revenueCustomPopoverOpen}
                minIso={revenueBoundsIso?.min ?? ""}
                maxIso={revenueBoundsIso?.max ?? ""}
                committedFrom={revenueCustomIso?.from ?? ""}
                committedTo={revenueCustomIso?.to ?? ""}
                title={at("stats_revenue_custom_range_title", {}, "")}
                triggerLabel={at("stats_revenue_period_custom", {}, "Custom")}
                applyLabel={at("stats_revenue_custom_range_apply", {}, "Apply")}
                locale={currentLang}
                isActive={revenueRangeMode === "custom"}
                onApply={onCustomRangeApply}
              />
            </div>
          </div>
          <AdminRevenueTabs
            value={revenueGranularity}
            items={REVENUE_GRANULARITIES.map((value) => ({
              value,
              label: at(`stats_revenue_granularity_${value}`, {}, value),
            }))}
            ariaLabel={at("stats_revenue_granularity_aria", {}, "")}
            variant="granularity"
            onValueChange={setRevenueGranularity}
          />
          <p class="admin-revenue-chart-hint admin-muted">{at(revenueChartHintKey(), {}, "")}</p>
          {#if revenueHasValues}
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
                  locale={currentLang}
                  granularity={revenueGranularity}
                  legendTimeLabel={at("stats_revenue_chart_uplot_time", {}, "Time")}
                  legendValueLabel={at("stats_revenue_chart_uplot_value", {}, "Value")}
                  legendDeltaLabel={at("stats_revenue_chart_uplot_delta", {}, "Change")}
                />
              {:else}
                <AdminChartSkeleton plotHeight={REVENUE_CHART_MAX_CSS_HEIGHT} />
              {/if}
            </div>
          {:else}
            <div class="admin-revenue-svg-frame admin-revenue-svg-frame--chart">
              <AdminChartEmptyState
                label={at("stats_revenue_no_chart", {}, "No data yet")}
                plotHeight={REVENUE_CHART_MAX_CSS_HEIGHT}
              />
            </div>
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
        <PaymentTable
          {at}
          payments={recentPayments}
          loading={statsLoading}
          sort={recentPaymentsSort}
          skeletonRows={5}
          emptyLabel={at("no_data", {}, "")}
          {fmtDate}
          {fmtMoney}
          {paymentStatusVariant}
          onSort={(sort) => (recentPaymentsSort = sort)}
          {onOpenUserCard}
        />
      </Card.Content>
    </Card.Root>
  </AdminDashboardStack>
{/if}

<style>
  :global(.admin-stats-audience-card .admin-cn-card-header) {
    padding-bottom: 18px;
  }

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
</style>
