<script lang="ts">
  import {
    Activity,
    FileText,
    Radio,
    Server,
    TrendingDown,
    TrendingUp,
    User,
    Zap,
  } from "$components/ui/icons.js";
  import { getContext, onMount } from "svelte";

  import Badge from "$components/ui/badge.svelte";
  import { ScrollArea } from "$components/ui/index.js";
  import * as Card from "$components/ui/card/index.js";
  import {
    AdminDashboardGrid,
    AdminDashboardStack,
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminRevenueChart,
    AdminRevenueCustomRangePopover,
    AdminSectionHeader,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
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
  import type { PaymentOut, PaymentsStore } from "$lib/admin/stores/paymentsStore";
  import type { StatsState, StatsStore } from "$lib/admin/stores/statsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type FormatterFn = (value: unknown, currency?: string) => string;
  type DateFormatterFn = (value: unknown) => string;
  type AdminBadgeVariant = "success" | "danger" | "warning" | "muted";
  type RevenueGranularity = "day" | "week" | "month";
  type RevenueRangeMode = "preset" | "custom";
  type IsoRange = { from: string; to: string };

  let {
    at,
    fmtDate = (value) => String(value ?? ""),
    fmtDateShort = (value) => String(value ?? ""),
    fmtMoney = (value) => String(value ?? ""),
    paymentStatusVariant = () => "muted",
    onOpenUserCard = () => {},
  }: {
    at: TranslateFn;
    fmtDate?: DateFormatterFn;
    fmtDateShort?: DateFormatterFn;
    fmtMoney?: FormatterFn;
    paymentStatusVariant?: (status: unknown) => AdminBadgeVariant;
    onOpenUserCard?: (userId: unknown) => void;
  } = $props();

  const paymentsStore = getContext<PaymentsStore>("paymentsStore");
  const statsStore = getContext<StatsStore>("statsStore");

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

  const PANEL_NODE_TILE_LIMIT = 10;

  const REVENUE_CHART_MAX_CSS_HEIGHT = 204;

  const REVENUE_PRESET_DAYS = [7, 14, 30, 90, 180, 365];

  let revenueRangeMode = $state<RevenueRangeMode>("preset");
  let revenuePresetDays = $state(14);
  let revenueCustomIso = $state<IsoRange | null>(null);
  let revenueGranularity = $state<RevenueGranularity>("day");
  let revenueCustomPopoverOpen = $state(false);

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
    at("user", {}, "Пользователь"),
    at("payments_col_user_id", {}, "ID"),
    at("payments_col_traffic_regular", {}, "Основной трафик"),
    at("payments_col_traffic_premium", {}, "Премиум"),
    at("amount", {}, "Сумма"),
    at("provider", {}, "Провайдер"),
    at("description", {}, "Описание"),
    at("status", {}, "Статус"),
    at("date", {}, "Дата"),
  ]);
  const recentPayments: PaymentOut[] = $derived((stats?.recent_payments || []).slice(0, 10));

  onMount(() => {
    void statsStore.loadStats();
  });
</script>

{#if statsError}
  <AdminEmptyState>{at("stats_error", { error: statsError }, "")}</AdminEmptyState>
{:else if showSkeleton}
  <AdminDashboardStack>
    <AdminSectionHeader title={at("stats_section_audience", {}, "")} />
    <AdminDashboardGrid columns={3}>
      {#each Array(3) as _, i (i)}
        <Card.Root class="admin-cn-card-skeleton">
          <Card.Header>
            <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span>
            <span
              class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong"
              style="width:72%"
            ></span>
          </Card.Header>
          <Card.Footer class="admin-cn-card-footer--stack">
            <span class="admin-skeleton admin-skeleton-line" style="width:88%"></span>
            <span
              class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"
              style="width:60%"
            ></span>
          </Card.Footer>
        </Card.Root>
      {/each}
    </AdminDashboardGrid>

    <AdminSectionHeader
      title={at("stats_section_revenue", {}, "")}
      description={at("stats_section_revenue_hint", {}, "")}
    />
    <Card.Root class="admin-cn-card-skeleton admin-cn-card-skeleton--tall">
      <Card.Header>
        <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span>
        <span
          class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong"
          style="width:48%"
        ></span>
      </Card.Header>
      <Card.Content>
        <div class="admin-revenue-kpis" aria-hidden="true">
          {#each Array(6) as _, i (i)}
            <div class="admin-revenue-kpi">
              <span
                class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"
                style="width:72%"
              ></span>
              <span
                class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong"
                style="width:58%;height:20px;margin-top:4px"
              ></span>
            </div>
          {/each}
          <div class="admin-revenue-kpi admin-revenue-kpi--wide">
            <span
              class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"
              style="width:46%"
            ></span>
            <span
              class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong"
              style="width:36%;height:20px;margin-top:4px"
            ></span>
            <span
              class="admin-skeleton admin-skeleton-line"
              style="width:92%;height:9px;margin-top:6px"
            ></span>
          </div>
        </div>
        <div class="admin-revenue-chart">
          <div class="admin-revenue-chart-title">
            <span
              class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"
              style="width:42%"
            ></span>
          </div>
          <div class="admin-revenue-svg-frame">
            <div
              class="admin-skeleton admin-revenue-chart-skeleton"
              style="display:block;width:100%;border-radius:0"
            ></div>
          </div>
          <div class="admin-revenue-xlabels" aria-hidden="true">
            {#each Array(4) as _, j (j)}
              <span
                class="admin-skeleton admin-skeleton-line"
                style="display:block;height:8px;flex:1;max-width:24%"
              ></span>
            {/each}
          </div>
        </div>
      </Card.Content>
    </Card.Root>

    <AdminSectionHeader
      title={at("stats_section_panel", {}, "")}
      description={at("stats_section_panel_hint", {}, "")}
    />
    <Card.Root class="admin-cn-card-skeleton admin-cn-card-skeleton--tall">
      <Card.Content class="admin-cn-card-content admin-panel-dash-card">
        <div class="admin-panel-dash">
          <div class="admin-panel-dash-tiles" aria-hidden="true">
            {#each Array(9) as _, k (k)}
              <div class="admin-panel-dash-tile">
                <span
                  class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"
                  style="width:58%"
                ></span>
                <span
                  class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong"
                  style="width:44%;height:22px;margin-top:6px"
                ></span>
              </div>
            {/each}
          </div>
          <div class="admin-panel-dash-nodes">
            <div class="admin-panel-dash-nodes-head">
              <span class="admin-skeleton admin-skeleton-line" style="width:40%;height:12px"></span>
              <span
                class="admin-skeleton admin-skeleton-line"
                style="width:78%;height:9px;margin-top:6px"
              ></span>
            </div>
            <ScrollArea class="admin-panel-dash-nodes-scroll" maxHeight="240px">
              <div class="admin-panel-dash-nodes-grid">
                {#each Array(4) as _, m (m)}
                  <div class="admin-panel-dash-node">
                    <span class="admin-skeleton admin-skeleton-line" style="width:82%"></span>
                    <span
                      class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong"
                      style="width:52%;height:16px;margin-top:6px"
                    ></span>
                    <span
                      class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"
                      style="width:44%;margin-top:6px"
                    ></span>
                  </div>
                {/each}
              </div>
            </ScrollArea>
          </div>
        </div>
      </Card.Content>
    </Card.Root>

    <Card.Root>
      <Card.Content
        class="admin-cn-card-content--flush"
        style="padding-top:12px;padding-bottom:12px;"
      >
        <div class="admin-sync-strip" style="border:0;background:transparent;padding:0;">
          <span
            class="admin-skeleton admin-skeleton-line"
            style="display:block;width:min(100%, 340px);height:12px"
          ></span>
          <span
            class="admin-skeleton admin-skeleton-line"
            style="display:block;width:min(100%, 220px);height:11px;margin-top:8px"
          ></span>
        </div>
      </Card.Content>
    </Card.Root>

    <Card.Root>
      <Card.Header class="admin-cn-card-header--lead">
        <span class="admin-skeleton admin-skeleton-line" style="width:44%;height:14px"></span>
      </Card.Header>
      <Card.Content class="admin-cn-card-content--flush">
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
      </Card.Content>
    </Card.Root>
  </AdminDashboardStack>
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
          <Card.Title>{users.total_users ?? 0}</Card.Title>
          <Card.Action>
            <Badge variant="outline">+{users.active_today ?? 0}</Badge>
          </Card.Action>
        </Card.Header>
        <Card.Footer class="admin-cn-card-footer--stack">
          <div class="admin-cn-card-footer-primary">
            {at("stats_trend_banned", { count: users.banned_users ?? 0 }, "")}
          </div>
          <div class="admin-cn-card-footer-muted">
            {at("stats_trend_referrals", { count: users.referral_users ?? 0 }, "")}
          </div>
        </Card.Footer>
      </Card.Root>

      <Card.Root>
        <Card.Header>
          <Card.Description>{at("stats_label_active_subs", {}, "")}</Card.Description>
          <Card.Title>{users.active_subscriptions ?? 0}</Card.Title>
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
            {at("stats_trend_paid", { count: users.paid_subscriptions ?? 0 }, "")}
            · {at("stats_trend_free", { count: users.free_subscription_users ?? 0 }, "")}
            · {at("stats_trend_trials", { count: users.trial_users ?? 0 }, "")}
          </div>
          <div class="admin-cn-card-footer-muted">
            {at("stats_card_active_subs_caption", {}, "")}
          </div>
        </Card.Footer>
      </Card.Root>

      <Card.Root>
        <Card.Header>
          <Card.Description>{at("stats_label_inactive", {}, "")}</Card.Description>
          <Card.Title>{users.inactive_users ?? 0}</Card.Title>
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
            {at(
              "stats_trend_expired_subscriptions",
              { count: users.expired_subscription_users ?? 0 },
              ""
            )}
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
              <AdminRevenueChart
                series={revenueChartSeries}
                plotHeight={REVENUE_CHART_MAX_CSS_HEIGHT}
                {fmtMoney}
                {currency}
                legendTimeLabel={at("stats_revenue_chart_uplot_time", {}, "Time")}
                legendValueLabel={at("stats_revenue_chart_uplot_value", {}, "Value")}
              />
            </div>
          {:else}
            <p class="admin-muted">{at("stats_revenue_no_chart", {}, "")}</p>
          {/if}
        </div>
      </Card.Content>
    </Card.Root>

    <AdminSectionHeader
      title={at("stats_section_panel", {}, "")}
      description={panelPayload?.error
        ? at("stats_panel_unavailable", {}, "")
        : panelMetrics
          ? at("stats_section_panel_hint", {}, "")
          : ""}
    />

    {#if panelPayload?.error}
      <p class="admin-muted" style="margin:0;">{at("stats_panel_unavailable_detail", {}, "")}</p>
    {:else if panelMetrics}
      <Card.Root>
        <Card.Content class="admin-cn-card-content admin-panel-dash-card">
          <div class="admin-panel-dash">
            <div
              class="admin-panel-dash-tiles"
              role="group"
              aria-label={at("stats_section_panel", {}, "")}
            >
              <div class="admin-panel-dash-tile">
                <div class="admin-panel-dash-tile-label">
                  <span class="admin-panel-dash-ico" aria-hidden="true"><Radio size={12} /></span>
                  {at("stats_panel_online", {}, "")}
                </div>
                <div class="admin-panel-dash-tile-value">{panelMetrics.onlineNow}</div>
              </div>
              <div class="admin-panel-dash-tile">
                <div class="admin-panel-dash-tile-label">{at("stats_panel_active", {}, "")}</div>
                <div class="admin-panel-dash-tile-value">{panelMetrics.active}</div>
              </div>
              <div class="admin-panel-dash-tile">
                <div class="admin-panel-dash-tile-label">
                  <span class="admin-panel-dash-ico" aria-hidden="true"><Activity size={12} /></span
                  >
                  {at("stats_panel_total_users", {}, "")}
                </div>
                <div class="admin-panel-dash-tile-value">{panelMetrics.totalPanelUsers}</div>
              </div>
              <div class="admin-panel-dash-tile">
                <div class="admin-panel-dash-tile-label">{at("stats_panel_expired", {}, "")}</div>
                <div class="admin-panel-dash-tile-value">{panelMetrics.expired}</div>
              </div>
              <div class="admin-panel-dash-tile">
                <div class="admin-panel-dash-tile-label">{at("stats_panel_disabled", {}, "")}</div>
                <div class="admin-panel-dash-tile-value">{panelMetrics.disabled}</div>
              </div>
              <div class="admin-panel-dash-tile">
                <div class="admin-panel-dash-tile-label">{at("stats_panel_limited", {}, "")}</div>
                <div class="admin-panel-dash-tile-value">{panelMetrics.limited}</div>
              </div>
              {#if panelNodesListedCount > 0}
                <div
                  class="admin-panel-dash-tile"
                  title={at("stats_panel_nodes_online_hint", {}, "")}
                >
                  <div class="admin-panel-dash-tile-label">
                    <span class="admin-panel-dash-ico" aria-hidden="true"><Server size={12} /></span
                    >
                    {at("stats_panel_nodes_online", {}, "")}
                  </div>
                  <div class="admin-panel-dash-tile-value">{panelNodesListedCount}</div>
                </div>
              {/if}
              {#if panelMetrics.memPct != null}
                <div class="admin-panel-dash-tile">
                  <div class="admin-panel-dash-tile-label">{at("stats_panel_memory", {}, "")}</div>
                  <div class="admin-panel-dash-tile-value">{panelMetrics.memPct.toFixed(1)}%</div>
                </div>
              {/if}
              {#if panelMetrics.cpuPct != null}
                <div class="admin-panel-dash-tile">
                  <div class="admin-panel-dash-tile-label">
                    <span class="admin-panel-dash-ico" aria-hidden="true"><Zap size={12} /></span>
                    {at("stats_panel_cpu", {}, "")}
                  </div>
                  <div class="admin-panel-dash-tile-value">{panelMetrics.cpuPct.toFixed(1)}%</div>
                </div>
              {/if}
              {#if panelBw?.week != null}
                <div class="admin-panel-dash-tile admin-panel-dash-tile--wide">
                  <div class="admin-panel-dash-tile-label">{at("stats_panel_bw_week", {}, "")}</div>
                  <div class="admin-panel-dash-tile-value admin-panel-dash-tile-value--sm">
                    {panelBw.week}
                  </div>
                </div>
              {/if}
              {#if panelBw?.month != null}
                <div class="admin-panel-dash-tile admin-panel-dash-tile--wide">
                  <div class="admin-panel-dash-tile-label">
                    {at("stats_panel_bw_month", {}, "")}
                  </div>
                  <div class="admin-panel-dash-tile-value admin-panel-dash-tile-value--sm">
                    {panelBw.month}
                  </div>
                </div>
              {/if}
            </div>

            {#if panelNodeTraffic?.seven?.length}
              <div class="admin-panel-dash-nodes">
                <div class="admin-panel-dash-nodes-head">
                  <h3 class="admin-panel-dash-nodes-title">
                    {at("stats_panel_inner_nodes", {}, "")}
                  </h3>
                  <p class="admin-panel-dash-nodes-hint">
                    {at("stats_panel_inner_nodes_hint", {}, "")}
                  </p>
                </div>
                <ScrollArea class="admin-panel-dash-nodes-scroll" maxHeight="240px">
                  <div class="admin-panel-dash-nodes-grid">
                    {#each panelNodeTraffic.seven.slice(0, PANEL_NODE_TILE_LIMIT) as node}
                      <div class="admin-panel-dash-node">
                        <div class="admin-panel-dash-node-name">{node.label}</div>
                        <div class="admin-panel-dash-node-value">{node.value}</div>
                        {#if node.online != null}
                          <div class="admin-panel-dash-node-meta">
                            {at("stats_panel_node_users_online", { count: node.online }, "")}
                          </div>
                        {/if}
                      </div>
                    {/each}
                  </div>
                </ScrollArea>
                {#if panelNodeTraffic.seven.length > PANEL_NODE_TILE_LIMIT}
                  <p class="admin-panel-dash-nodes-more">
                    {at(
                      "stats_panel_nodes_overflow",
                      { count: panelNodeTraffic.seven.length - PANEL_NODE_TILE_LIMIT },
                      ""
                    )}
                  </p>
                {/if}
              </div>
            {:else if panelPayload?.nodes && typeof panelPayload.nodes === "object" && Object.keys(panelPayload.nodes).length > 0}
              <p class="admin-panel-dash-nodes-empty">{at("stats_panel_nodes_empty", {}, "")}</p>
            {/if}
          </div>
        </Card.Content>
      </Card.Root>
    {/if}

    <Card.Root>
      <Card.Content
        class="admin-cn-card-content--flush"
        style="padding-top:12px;padding-bottom:12px;"
      >
        <div class="admin-sync-strip" style="border:0;background:transparent;padding:0;">
          <span
            ><strong>{at("stats_sync_label", {}, "")}:</strong>
            {stats.panel_sync?.status ?? "—"}{#if stats.panel_sync?.last_sync_time}
              · {at("stats_sync_last", {}, "")}: {fmtDateShort(
                stats.panel_sync.last_sync_time
              )}{/if}</span
          >
          {#if stats.panel_sync && (stats.panel_sync.users_processed > 0 || stats.panel_sync.subscriptions_synced > 0)}
            <span
              >{at(
                "stats_sync_processed",
                {
                  users: stats.panel_sync.users_processed,
                  subs: stats.panel_sync.subscriptions_synced,
                },
                ""
              )}</span
            >
          {/if}
          {#if stats.queue}
            <span
              ><strong>{at("stats_label_queue", {}, "")}:</strong>
              {stats.queue.user_queue_size ?? 0}{at("stats_queue_users", {}, "")}, {stats.queue
                .group_queue_size ?? 0}{at("stats_queue_groups", {}, "")}</span
            >
          {/if}
        </div>
      </Card.Content>
    </Card.Root>

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
                  <th>{at("user", {}, "Пользователь")}</th>
                  <th>{at("payments_col_user_id", {}, "ID")}</th>
                  <th>{at("payments_col_traffic_regular", {}, "Основной трафик")}</th>
                  <th>{at("payments_col_traffic_premium", {}, "Премиум")}</th>
                  <th>{at("amount", {}, "Сумма")}</th>
                  <th>{at("provider", {}, "Провайдер")}</th>
                  <th>{at("description", {}, "Описание")}</th>
                  <th>{at("status", {}, "Статус")}</th>
                  <th>{at("date", {}, "Дата")}</th>
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
                        title={at("payment_detail_open", {}, "Открыть платеж")}
                        aria-label={at("payment_detail_open", {}, "Открыть платеж")}
                        onclick={() => paymentsStore.openPayment(p)}
                      >
                        <FileText size={14} />
                        #{p.payment_id}
                      </AdminButton>
                    </td>
                    <td
                      class="admin-cell-user-with-action"
                      data-label={at("user", {}, "Пользователь")}
                    >
                      <span class="admin-payments-user-cell">
                        <AdminButton
                          class="admin-payments-user-btn"
                          variant="ghost"
                          size="icon"
                          title={at("payments_open_user", {}, "Открыть карточку пользователя")}
                          aria-label={at("payments_open_user", {}, "Открыть карточку пользователя")}
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
                      data-label={at("payments_col_traffic_regular", {}, "Основной трафик")}
                    >
                      {formatTrafficGbCell(p.traffic_regular_gb)}
                    </td>
                    <td
                      class="admin-cell-traffic-gb"
                      data-label={at("payments_col_traffic_premium", {}, "Премиум")}
                    >
                      {formatTrafficGbCell(p.traffic_premium_gb)}
                    </td>
                    <td data-label={at("amount", {}, "Сумма")}>
                      {fmtMoney(p.amount, p.currency ?? undefined)}
                    </td>
                    <td data-label={at("provider", {}, "Провайдер")}>{p.provider}</td>
                    <td class="admin-cell-wrap" data-label={at("description", {}, "Описание")}
                      >{paymentDescriptionDisplay(p, at)}</td
                    >
                    <td data-label={at("status", {}, "Статус")}>
                      <AdminBadge variant={paymentStatusVariant(p.status)}>{p.status}</AdminBadge>
                    </td>
                    <td data-label={at("date", {}, "Дата")}>{fmtDate(p.created_at)}</td>
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
