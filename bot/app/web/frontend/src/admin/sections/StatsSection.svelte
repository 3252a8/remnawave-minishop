<script>
  import { Activity, Radio, Server, TrendingDown, TrendingUp } from "$components/ui/icons.js";
  import { getContext, onMount } from "svelte";

  import Badge from "$components/ui/badge.svelte";
  import * as Card from "$components/ui/card/index.js";
  import {
    AdminDashboardGrid,
    AdminDashboardStack,
    AdminBadge,
    AdminEmptyState,
    AdminSectionHeader,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";

  export let at;
  export let fmtDate = (value) => value;
  export let fmtDateShort = (value) => value;
  export let fmtMoney = (value) => value;
  export let paymentStatusVariant = () => "muted";

  const statsStore = getContext("statsStore");

  $: ({
    stats,
    statsError,
    statsLoading,
  } = $statsStore);

  $: showSkeleton = !stats && !statsError;

  $: currency = stats?.currency_symbol || "RUB";
  $: fin = stats?.financial || {};
  $: users = stats?.users || {};
  $: panelPayload = stats?.panel;
  $: panelMetrics =
    panelPayload && !panelPayload.error ? parsePanelSystem(panelPayload) : null;
  $: panelBw =
    panelPayload && !panelPayload.error ? parsePanelBandwidth(panelPayload) : null;

  $: dailySeries = Array.isArray(fin.daily_series) ? fin.daily_series : [];
  $: revenueKpis = computeRevenueKpis(fin, dailySeries);
  $: chartModel = buildRevenueChartModel(dailySeries, fmtDateShort);
  $: recentPaymentHeaders = [
    at("id", {}, ""),
    at("user", {}, ""),
    at("amount", {}, ""),
    at("provider", {}, ""),
    at("status", {}, ""),
    at("date", {}, ""),
  ];

  function parsePanelSystem(panel) {
    const system = panel?.system;
    if (!system || typeof system !== "object") return null;
    const u = system.users || {};
    const statusCounts = u.statusCounts || {};
    const onlineStats = system.onlineStats || {};
    const mem = system.memory || {};
    const memTotal = Number(mem.total) || 0;
    const memUsed = Number(mem.used) || 0;
    const memPct = memTotal > 0 ? (memUsed / memTotal) * 100 : null;
    const nodes = system.nodes || {};
    return {
      onlineNow: onlineStats.onlineNow ?? 0,
      active: statusCounts.ACTIVE ?? 0,
      disabled: statusCounts.DISABLED ?? 0,
      expired: statusCounts.EXPIRED ?? 0,
      limited: statusCounts.LIMITED ?? 0,
      totalPanelUsers: u.totalUsers ?? 0,
      nodesOnline: nodes.totalOnline != null ? nodes.totalOnline : null,
      memPct,
    };
  }

  function parsePanelBandwidth(panel) {
    const bw = panel?.bandwidth;
    if (!bw || typeof bw !== "object") return null;
    const week = bw.bandwidthLastSevenDays?.current;
    const month =
      bw.bandwidthLast30Days?.current ?? bw.bandwidthLastThirtyDays?.current;
    if (week == null && month == null) return null;
    return { week, month };
  }

  function computeRevenueKpis(financial, series) {
    const amounts = series.map((p) => Number(p.amount) || 0);
    const n = amounts.length;
    const last7 = n ? amounts.slice(-7).reduce((a, b) => a + b, 0) : 0;
    const prev7 = n > 7 ? amounts.slice(-14, -7).reduce((a, b) => a + b, 0) : 0;
    let growthPct = null;
    if (n >= 14 && prev7 > 0) growthPct = ((last7 - prev7) / prev7) * 100;
    const tc = Number(financial.today_payments_count) || 0;
    const tr = Number(financial.today_revenue) || 0;
    const avgToday = tc > 0 ? tr / tc : null;
    const total14 = amounts.reduce((a, b) => a + b, 0);
    const maxY = Math.max(...amounts, 1e-9);
    return { last7, prev7, growthPct, avgToday, total14, maxY, amounts, n };
  }

  function buildRevenueChartModel(series, fmtShort) {
    const W = 360;
    const H = 168;
    const pad = { t: 12, r: 10, b: 26, l: 8 };
    const innerW = W - pad.l - pad.r;
    const innerH = H - pad.t - pad.b;
    const amounts = series.map((p) => Number(p.amount) || 0);
    const n = amounts.length;
    if (!n) return null;
    const maxY = Math.max(...amounts, 1e-9);
    const pts = amounts.map((amt, i) => {
      const x = pad.l + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
      const y = pad.t + innerH - (amt / maxY) * innerH;
      return { x, y, amt, date: series[i]?.date };
    });
    const lineD = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join("");
    const baseY = (pad.t + innerH).toFixed(1);
    const areaD = `${lineD} L${pts[n - 1].x.toFixed(1)},${baseY} L${pts[0].x.toFixed(1)},${baseY} Z`;
    const pickIdx = (() => {
      if (n === 1) return [0];
      const u = new Set([0, Math.floor((n - 1) / 3), Math.floor((2 * (n - 1)) / 3), n - 1]);
      return [...u].sort((a, b) => a - b);
    })();
    const ticks = pickIdx.map((i) => ({
      x: pts[i].x,
      label: fmtShort(series[i]?.date),
    }));
    const gridYs = [0.33, 0.66].map((g) => pad.t + innerH * (1 - g));
    return { lineD, areaD, ticks, W, H, maxY, gridYs, pad, innerW, innerH };
  }

  function growthBadgeVariant(pct) {
    if (pct == null) return "outline";
    if (pct >= 0) return "default";
    return "destructive";
  }

  onMount(() => {
    statsStore.loadStats();
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
            <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong" style="width:72%"></span>
          </Card.Header>
          <Card.Footer class="admin-cn-card-footer--stack">
            <span class="admin-skeleton admin-skeleton-line" style="width:88%"></span>
            <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny" style="width:60%"></span>
          </Card.Footer>
        </Card.Root>
      {/each}
    </AdminDashboardGrid>
    <Card.Root class="admin-cn-card-skeleton">
      <Card.Header>
        <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span>
        <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong" style="width:40%"></span>
      </Card.Header>
      <Card.Content class="admin-cn-card-content--flush">
        <div class="admin-revenue-svg-frame">
          <div class="admin-skeleton" style="height:168px;border-radius:10px;"></div>
        </div>
      </Card.Content>
    </Card.Root>
    <AdminSectionHeader title={at("stats_recent_payments", {}, "")} />
    <AdminTableSkeleton headers={recentPaymentHeaders} rows={6} widths={["48px", "120px", "78px", "82px", "72px", "96px"]} />
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
          <Card.Description>{at("stats_label_paid_subs", {}, "")}</Card.Description>
          <Card.Title>{users.paid_subscriptions ?? 0}</Card.Title>
          <Card.Action>
            <Badge variant="outline">{users.trial_users ?? 0}</Badge>
          </Card.Action>
        </Card.Header>
        <Card.Footer class="admin-cn-card-footer--stack">
          <div class="admin-cn-card-footer-primary">
            {at("stats_trend_trials", { count: users.trial_users ?? 0 }, "")}
          </div>
          <div class="admin-cn-card-footer-muted">{at("stats_card_paid_caption", {}, "")}</div>
        </Card.Footer>
      </Card.Root>

      <Card.Root>
        <Card.Header>
          <Card.Description>{at("stats_label_inactive", {}, "")}</Card.Description>
          <Card.Title>{users.inactive_users ?? 0}</Card.Title>
          <Card.Action>
            <Badge variant="outline">{users.total_users ? Math.round(((users.inactive_users ?? 0) / (users.total_users || 1)) * 100) : 0}%</Badge>
          </Card.Action>
        </Card.Header>
        <Card.Footer class="admin-cn-card-footer--stack">
          <div class="admin-cn-card-footer-primary">
            {at("stats_trend_new_today", { count: users.active_today ?? 0 }, "")}
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
            <div class="admin-revenue-kpi-label">{at("stats_trend_payments", { count: fin.today_payments_count ?? 0 }, "")}</div>
            <div class="admin-revenue-kpi-value">{fin.today_payments_count ?? 0}</div>
          </div>
          <div class="admin-revenue-kpi">
            <div class="admin-revenue-kpi-label">{at("stats_revenue_avg_ticket_label", {}, "")}</div>
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
          <div class="admin-revenue-chart-title">{at("stats_revenue_chart_title", {}, "")}</div>
          {#if chartModel}
            <div class="admin-revenue-svg-frame" role="img" aria-label={at("stats_revenue_chart_aria", {}, "")}>
              <svg class="admin-revenue-svg" viewBox="0 0 {chartModel.W} {chartModel.H}" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="adminRevenueFillDashboard" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="var(--admin-muted)" stop-opacity="0.28" />
                    <stop offset="100%" stop-color="var(--admin-muted)" stop-opacity="0" />
                  </linearGradient>
                </defs>
                {#each chartModel.gridYs as gy}
                  <line x1={chartModel.pad.l} y1={gy} x2={chartModel.W - chartModel.pad.r} y2={gy} stroke="var(--admin-border)" stroke-opacity="0.45" stroke-width="1" />
                {/each}
                <path d={chartModel.areaD} fill="url(#adminRevenueFillDashboard)" stroke="none" />
                <path
                  d={chartModel.lineD}
                  fill="none"
                  stroke="color-mix(in srgb, var(--admin-muted) 55%, var(--admin-text))"
                  stroke-width="2"
                  stroke-linejoin="round"
                  stroke-linecap="round"
                />
              </svg>
            </div>
            <div class="admin-revenue-xlabels">
              {#each chartModel.ticks as tk}
                <span>{tk.label}</span>
              {/each}
            </div>
          {:else}
            <p class="admin-muted">{at("stats_revenue_no_chart", {}, "")}</p>
          {/if}
        </div>
      </Card.Content>
    </Card.Root>

    <AdminSectionHeader
      title={at("stats_section_panel", {}, "")}
      description={panelPayload?.error ? at("stats_panel_unavailable", {}, "") : panelMetrics ? at("stats_section_panel_hint", {}, "") : ""}
    />

    {#if panelPayload?.error}
      <p class="admin-muted" style="margin:0;">{at("stats_panel_unavailable_detail", {}, "")}</p>
    {:else if panelMetrics}
      <Card.Root>
        <Card.Content>
          <div class="admin-dashboard-panel-metrics">
            <div class="admin-dashboard-panel-metric">
              <span><Radio size={12} /> {at("stats_panel_online", {}, "")}</span>
              <strong>{panelMetrics.onlineNow}</strong>
            </div>
            <div class="admin-dashboard-panel-metric">
              <span>{at("stats_panel_active", {}, "")}</span>
              <strong>{panelMetrics.active}</strong>
            </div>
            <div class="admin-dashboard-panel-metric">
              <span>{at("stats_panel_expired", {}, "")}</span>
              <strong>{panelMetrics.expired}</strong>
            </div>
            <div class="admin-dashboard-panel-metric">
              <span>{at("stats_panel_disabled", {}, "")}</span>
              <strong>{panelMetrics.disabled}</strong>
            </div>
            <div class="admin-dashboard-panel-metric">
              <span>{at("stats_panel_limited", {}, "")}</span>
              <strong>{panelMetrics.limited}</strong>
            </div>
            <div class="admin-dashboard-panel-metric">
              <span><Activity size={12} /> {at("stats_panel_total_users", {}, "")}</span>
              <strong>{panelMetrics.totalPanelUsers}</strong>
            </div>
            {#if panelMetrics.nodesOnline != null}
              <div class="admin-dashboard-panel-metric">
                <span><Server size={12} /> {at("stats_panel_nodes_online", {}, "")}</span>
                <strong>{panelMetrics.nodesOnline}</strong>
              </div>
            {/if}
            {#if panelMetrics.memPct != null}
              <div class="admin-dashboard-panel-metric">
                <span>{at("stats_panel_memory", {}, "")}</span>
                <strong>{panelMetrics.memPct.toFixed(1)}%</strong>
              </div>
            {/if}
          </div>
          {#if panelBw && (panelBw.week != null || panelBw.month != null)}
            <dl class="admin-dashboard-panel-bandwidth">
              {#if panelBw.week != null}
                <div>
                  <dt>{at("stats_panel_bw_week", {}, "")}</dt>
                  <dd>{panelBw.week}</dd>
                </div>
              {/if}
              {#if panelBw.month != null}
                <div>
                  <dt>{at("stats_panel_bw_month", {}, "")}</dt>
                  <dd>{panelBw.month}</dd>
                </div>
              {/if}
            </dl>
          {/if}
        </Card.Content>
      </Card.Root>
    {/if}

    <Card.Root>
      <Card.Content class="admin-cn-card-content--flush" style="padding-top:12px;padding-bottom:12px;">
        <div class="admin-sync-strip" style="border:0;background:transparent;padding:0;">
          <span
            ><strong>{at("stats_sync_label", {}, "")}:</strong>
            {stats.panel_sync?.status ?? "—"}{#if stats.panel_sync?.last_sync_time}
              · {at("stats_sync_last", {}, "")}: {fmtDateShort(stats.panel_sync.last_sync_time)}{/if}</span
          >
          {#if stats.panel_sync && (stats.panel_sync.users_processed > 0 || stats.panel_sync.subscriptions_synced > 0)}
            <span
              >{at("stats_sync_processed", { users: stats.panel_sync.users_processed, subs: stats.panel_sync.subscriptions_synced }, "")}</span
            >
          {/if}
          {#if stats.queue}
            <span
              ><strong>{at("stats_label_queue", {}, "")}:</strong>
              {stats.queue.user_queue_size ?? 0}{at("stats_queue_users", {}, "")}, {stats.queue.group_queue_size ?? 0}{at("stats_queue_groups", {}, "")}</span
            >
          {/if}
        </div>
      </Card.Content>
    </Card.Root>

    <Card.Root>
      <Card.Header class="admin-cn-card-header--lead">
        <Card.Title class="admin-cn-card-title--section">{at("stats_recent_payments", {}, "")}</Card.Title>
        <Card.Description>{at("stats_records_count", { count: (stats.recent_payments || []).length }, "")}</Card.Description>
      </Card.Header>
      <Card.Content class="admin-cn-card-content--flush">
        <div class="admin-table-wrap">
          {#if statsLoading}
            <AdminTableSkeleton headers={recentPaymentHeaders} rows={5} widths={["48px", "120px", "78px", "82px", "72px", "96px"]} />
          {:else if (stats.recent_payments || []).length}
            <AdminTable>
              <thead>
                <tr>
                  <th>{at("id", {}, "")}</th>
                  <th>{at("user", {}, "")}</th>
                  <th>{at("amount", {}, "")}</th>
                  <th>{at("provider", {}, "")}</th>
                  <th>{at("status", {}, "")}</th>
                  <th>{at("date", {}, "")}</th>
                </tr>
              </thead>
              <tbody>
                {#each stats.recent_payments as p}
                  <tr>
                    <td class="admin-cell-id" data-label={at("id", {}, "")}>#{p.payment_id}</td>
                    <td data-label={at("user", {}, "")}>{p.user_label || p.user_id}</td>
                    <td data-label={at("amount", {}, "")}>{fmtMoney(p.amount, p.currency)}</td>
                    <td data-label={at("provider", {}, "")}>{p.provider}</td>
                    <td data-label={at("status", {}, "")}>
                      <AdminBadge variant={paymentStatusVariant(p.status)}>{p.status}</AdminBadge>
                    </td>
                    <td data-label={at("date", {}, "")}>{fmtDate(p.created_at)}</td>
                  </tr>
                {/each}
              </tbody>
            </AdminTable>
          {:else}
            <AdminEmptyState tone="card"><span class="admin-muted">{at("no_data", {}, "")}</span></AdminEmptyState>
          {/if}
        </div>
      </Card.Content>
    </Card.Root>
  </AdminDashboardStack>
{/if}
