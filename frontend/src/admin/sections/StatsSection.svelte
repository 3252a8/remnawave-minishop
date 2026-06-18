<script>
  import { Activity, Radio, Server, TrendingDown, TrendingUp, Zap } from "$components/ui/icons.js";
  import { getContext, onMount } from "svelte";

  import { fmtTrafficBytes } from "../../lib/admin/format.js";
  import Badge from "$components/ui/badge.svelte";
  import { ScrollArea } from "$components/ui/index.js";
  import * as Card from "$components/ui/card/index.js";
  import {
    AdminDashboardGrid,
    AdminDashboardStack,
    AdminBadge,
    AdminEmptyState,
    AdminPagination,
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
  import { createAdminDatatable, syncAdminDatatable } from "../../lib/admin/datatables.js";

  export let at;
  export let fmtDate = (value) => value;
  export let fmtDateShort = (value) => value;
  export let fmtMoney = (value) => value;
  export let paymentStatusVariant = () => "muted";

  const statsStore = getContext("statsStore");

  $: ({ stats, statsError, statsLoading } = $statsStore);

  $: showSkeleton = !stats && !statsError;

  $: currency = stats?.currency_symbol || "RUB";
  $: fin = stats?.financial || {};
  $: users = stats?.users || {};
  $: panelPayload = stats?.panel;
  $: panelMetrics = panelPayload && !panelPayload.error ? parsePanelSystem(panelPayload) : null;
  $: panelBw = panelPayload && !panelPayload.error ? parsePanelBandwidth(panelPayload) : null;
  $: panelNodeTraffic =
    panelPayload && !panelPayload.error ? parsePanelNodeTraffic(panelPayload) : null;
  /** Same rows as the «Per node (7 days)» block — not system.nodes.totalOnline from /system/stats */
  $: panelNodesListedCount = panelNodeTraffic?.seven?.length ?? 0;

  const PANEL_NODE_TILE_LIMIT = 10;

  const REVENUE_CHART_MAX_CSS_HEIGHT = 204;

  const REVENUE_PRESET_DAYS = [7, 14, 30, 90, 180, 365];
  const RECENT_PAYMENTS_PAGE_SIZE = 5;
  const recentPaymentsTable = createAdminDatatable([], {
    rowsPerPage: RECENT_PAYMENTS_PAGE_SIZE,
  });

  /** @type {"preset" | "custom"} */
  let revenueRangeMode = "preset";
  let revenuePresetDays = 14;
  /** @type {{ from: string; to: string } | null} */
  let revenueCustomIso = null;
  /** @type {"day" | "week" | "month"} */
  let revenueGranularity = "day";
  let revenueCustomPopoverOpen = false;

  $: dailySeries = Array.isArray(fin.daily_series) ? fin.daily_series : [];
  $: revenueBoundsIso =
    dailySeries.length > 0
      ? { min: dailySeries[0].date, max: dailySeries[dailySeries.length - 1].date }
      : null;

  $: revenueDailyFiltered = (() => {
    if (!dailySeries.length) return [];
    if (revenueRangeMode === "custom" && revenueCustomIso) {
      return filterDailyByIsoRange(dailySeries, revenueCustomIso.from, revenueCustomIso.to);
    }
    return sliceLastDays(dailySeries, revenuePresetDays);
  })();

  $: revenueChartSeries = aggregateRevenueSeries(revenueDailyFiltered, revenueGranularity);

  $: revenueKpis = computeRevenueKpis(fin, dailySeries);
  $: chartRangeSum = revenueChartSeries.reduce((a, p) => a + (Number(p.amount) || 0), 0);

  function setRevenuePresetDays(days) {
    const next = Number(days);
    if (!REVENUE_PRESET_DAYS.includes(next)) return;
    revenueRangeMode = "preset";
    revenuePresetDays = next;
    revenueCustomPopoverOpen = false;
  }

  function onCustomRangeApply({ fromIso, toIso }) {
    revenueRangeMode = "custom";
    revenueCustomIso = { from: fromIso, to: toIso };
  }

  function setRevenueGranularity(next) {
    const g = String(next);
    if (g !== "day" && g !== "week" && g !== "month") return;
    revenueGranularity = g;
  }

  function revenuePeriodLabel(days) {
    return at(`stats_revenue_period_${days}`, {}, `${days}d`);
  }

  function revenueChartHintKey() {
    if (revenueGranularity === "week") return "stats_revenue_chart_hint_week";
    if (revenueGranularity === "month") return "stats_revenue_chart_hint_month";
    return "stats_revenue_chart_hint";
  }

  $: revenueChartShortfall =
    revenueRangeMode === "preset" && dailySeries.length < revenuePresetDays;
  $: revenueCustomDaySpan =
    revenueRangeMode === "custom" && revenueCustomIso
      ? inclusiveDaySpan(revenueCustomIso.from, revenueCustomIso.to)
      : 0;
  $: recentPaymentHeaders = [
    at("id", {}, ""),
    at("user", {}, ""),
    at("amount", {}, ""),
    at("provider", {}, ""),
    at("status", {}, ""),
    at("date", {}, ""),
  ];
  $: syncAdminDatatable(recentPaymentsTable, stats?.recent_payments || []);
  $: recentPaymentsTotal = (stats?.recent_payments || []).length;
  $: if (recentPaymentsTable.currentPage > recentPaymentsTable.pageCount)
    recentPaymentsTable.setPage(recentPaymentsTable.pageCount || 1);

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
    const cpuRaw =
      system.cpu?.usage ??
      system.cpu?.usedPercent ??
      system.cpu?.percent ??
      system.cpuUsage ??
      system.cpuLoad;
    const cpuPct = Number(cpuRaw);
    return {
      onlineNow: onlineStats.onlineNow ?? 0,
      active: statusCounts.ACTIVE ?? 0,
      disabled: statusCounts.DISABLED ?? 0,
      expired: statusCounts.EXPIRED ?? 0,
      limited: statusCounts.LIMITED ?? 0,
      totalPanelUsers: u.totalUsers ?? 0,
      memPct,
      cpuPct: Number.isFinite(cpuPct) ? cpuPct : null,
    };
  }

  function parsePanelBandwidth(panel) {
    const bw = panel?.bandwidth;
    if (!bw || typeof bw !== "object") return null;
    const week = bw.bandwidthLastSevenDays?.current;
    const month = bw.bandwidthLast30Days?.current ?? bw.bandwidthLastThirtyDays?.current;
    if (week == null && month == null) return null;
    return { week, month };
  }

  function panelRowBytes(row) {
    if (!row || typeof row !== "object") return 0;
    const total = Number(row.total);
    if (Number.isFinite(total) && total > 0) return total;
    const up = Number(row.uploadBytes ?? row.uplinkBytes ?? row.uplink ?? row.up ?? row.upload);
    const down = Number(
      row.downloadBytes ?? row.downlinkBytes ?? row.downlink ?? row.down ?? row.download
    );
    const sum = (Number.isFinite(up) ? up : 0) + (Number.isFinite(down) ? down : 0);
    return sum > 0 ? sum : 0;
  }

  /** Remnawave node metrics: inboundsStats / outboundsStats use uplink+downlink per tag. */
  function sumDirectionPair(item) {
    if (!item || typeof item !== "object") return 0;
    const combined = Number(item.total ?? item.bytes ?? item.value);
    if (Number.isFinite(combined) && combined > 0) return combined;
    const up = Number(
      item.uplink ?? item.upload ?? item.uploadBytes ?? item.up ?? item.tx ?? item.sent
    );
    const down = Number(
      item.downlink ?? item.download ?? item.downloadBytes ?? item.down ?? item.rx ?? item.received
    );
    return (Number.isFinite(up) ? up : 0) + (Number.isFinite(down) ? down : 0);
  }

  function sumTaggedStatsList(arr) {
    if (!Array.isArray(arr)) return 0;
    return arr.reduce((acc, item) => acc + sumDirectionPair(item), 0);
  }

  /** Traffic bytes for one node record from GET /system/stats/nodes (current panel shape). */
  function trafficBytesFromNodeRecord(node) {
    if (!node || typeof node !== "object") return 0;
    let b =
      sumTaggedStatsList(node.inboundsStats) +
      sumTaggedStatsList(node.outboundsStats) +
      sumTaggedStatsList(node.inbounds_stats) +
      sumTaggedStatsList(node.outbounds_stats);
    if (b <= 0) b = panelRowBytes(node);
    const life = Number(
      node.totalBytesLifetime ?? node.totalBytes ?? node.bytesLifetime ?? node.totalTrafficBytes
    );
    if (b <= 0 && Number.isFinite(life) && life > 0) b = life;
    return b;
  }

  function isNodeMetricsShape(row) {
    if (!row || typeof row !== "object") return false;
    return (
      Array.isArray(row.inboundsStats) ||
      Array.isArray(row.outboundsStats) ||
      Array.isArray(row.inbounds_stats) ||
      Array.isArray(row.outbounds_stats)
    );
  }

  function panelRowLabel(row) {
    if (!row || typeof row !== "object") return "—";
    for (const k of ["nodeName", "node_name", "name", "nodeRemark", "remark", "label", "title"]) {
      const v = row[k];
      if (v != null && String(v).trim()) return String(v).trim();
    }
    const u = row.nodeUuid ?? row.node_uuid ?? row.uuid;
    if (u) return `${String(u).slice(0, 8)}…`;
    return "—";
  }

  function nodeRecordUuid(row) {
    if (!row || typeof row !== "object") return "";
    const u = row.nodeUuid ?? row.node_uuid ?? row.uuid ?? row.id;
    return u != null ? String(u) : "";
  }

  function nodeRecordDisplayName(row) {
    if (!row || typeof row !== "object") return "";
    for (const k of ["nodeName", "node_name", "name", "label", "title", "hostname"]) {
      const v = row[k];
      if (v != null && String(v).trim()) return String(v).trim();
    }
    return "";
  }

  function nodeRecordUsersOnline(row) {
    if (!row || typeof row !== "object") return null;
    const raw =
      row.usersOnline ??
      row.users_online ??
      row.onlineUsers ??
      row.online_users ??
      row.onlineUserCount ??
      row.online_user_count ??
      row.connectedUsers ??
      row.connected_users ??
      row.onlineNow;
    const n = Number(raw);
    if (Number.isFinite(n)) return n;
    const mg = row.metricGroups;
    if (mg && typeof mg === "object") {
      const v = Number(mg.onlineUsers ?? mg.online_users);
      if (Number.isFinite(v)) return v;
    }
    return null;
  }

  /** Node list shapes from GET /system/stats/nodes (varies by panel version). */
  function extractPanelNodesList(raw) {
    if (!raw) return [];
    if (Array.isArray(raw)) return raw;
    if (typeof raw !== "object") return [];
    if (Array.isArray(raw.nodes)) return raw.nodes;
    if (Array.isArray(raw.items)) return raw.items;
    if (Array.isArray(raw.data)) return raw.data;
    if (Array.isArray(raw.response)) return raw.response;
    return [];
  }

  /** UUID + display name -> online count from panel node metrics. */
  function buildNodeOnlineLookup(panel) {
    const byUuid = new Map();
    const byName = new Map();
    const list = extractPanelNodesList(panel?.nodes);
    for (const node of list) {
      if (!node || typeof node !== "object") continue;
      const online = nodeRecordUsersOnline(node);
      if (online == null) continue;
      const id = nodeRecordUuid(node);
      if (id) byUuid.set(id.toLowerCase(), online);
      const nm = nodeRecordDisplayName(node);
      if (nm) byName.set(nm.toLowerCase(), online);
    }
    return { byUuid, byName };
  }

  function formatTrafficCell(bytes, row, stringHint) {
    if (bytes > 0) return fmtTrafficBytes(bytes);
    const cur = row?.current;
    if (typeof cur === "string" && cur.trim()) return cur.trim();
    if (typeof stringHint === "string" && stringHint.trim()) return stringHint.trim();
    if (isNodeMetricsShape(row) && !bytes) return fmtTrafficBytes(0);
    return "—";
  }

  function buildNodeMetricsRows(nodes) {
    return nodes
      .filter((n) => n && typeof n === "object")
      .map((node) => {
        const bytes = trafficBytesFromNodeRecord(node);
        const uid = nodeRecordUuid(node);
        return {
          label: panelRowLabel(node),
          value: formatTrafficCell(bytes, node, ""),
          sort: bytes,
          uuid: uid || null,
          online: nodeRecordUsersOnline(node),
        };
      })
      .sort((a, b) => b.sort - a.sort);
  }

  /** Aggregate legacy arrays (daily rows per node, etc.). */
  function aggregatePanelNodeRows(rows) {
    if (!Array.isArray(rows) || !rows.length) return [];
    const map = new Map();
    for (const row of rows) {
      if (!row || typeof row !== "object") continue;
      const key = String(
        row.nodeUuid ?? row.node_uuid ?? row.uuid ?? row.nodeName ?? row.name ?? panelRowLabel(row)
      );
      const prev = map.get(key) || { label: panelRowLabel(row), bytes: 0, stringHint: "" };
      const add = isNodeMetricsShape(row) ? trafficBytesFromNodeRecord(row) : panelRowBytes(row);
      prev.bytes += add;
      const cur = row.current;
      if (typeof cur === "string" && cur.trim()) prev.stringHint = cur.trim();
      prev.label = panelRowLabel(row) || prev.label;
      map.set(key, prev);
    }
    return [...map.values()]
      .map((x) => ({
        label: x.label,
        value:
          x.bytes > 0
            ? fmtTrafficBytes(x.bytes)
            : x.stringHint && String(x.stringHint).trim()
              ? String(x.stringHint).trim()
              : "—",
        sort: x.bytes,
        uuid: null,
        online: null,
      }))
      .sort((a, b) => b.sort - a.sort);
  }

  function bandwidthRowUuid(n) {
    if (!n || typeof n !== "object") return "";
    const u = n.uuid ?? n.nodeUuid ?? n.node_uuid ?? n.id;
    return u != null ? String(u) : "";
  }

  function attachNodeOnlineToRows(rows, lookup) {
    if (!Array.isArray(rows) || !lookup) return rows;
    const { byUuid, byName } = lookup;
    if (!byUuid.size && !byName.size) return rows;
    return rows.map((r) => {
      let o = r.online;
      if (o == null && r.uuid) {
        const hit = byUuid.get(String(r.uuid).toLowerCase());
        if (hit != null) o = hit;
      }
      if (o == null && r.label && typeof r.label === "string") {
        const hit = byName.get(r.label.trim().toLowerCase());
        if (hit != null) o = hit;
      }
      if (o != null) return { ...r, online: o };
      return r;
    });
  }

  /** Panel analytics: GET /bandwidth-stats/nodes — totals per node for the selected range (bytes). */
  function parseNodesBandwidthTop(panel) {
    const nb = panel?.nodes_bandwidth;
    if (!nb || typeof nb !== "object") return null;
    const top = nb.topNodes;
    if (Array.isArray(top) && top.length) {
      const rows = top.map((n) => {
        const total = Number(n?.total ?? n?.bytes ?? 0);
        const uuid = bandwidthRowUuid(n);
        const label =
          (typeof n?.name === "string" && n.name.trim()) ||
          (typeof n?.nodeName === "string" && n.nodeName.trim()) ||
          (uuid ? `${uuid.slice(0, 8)}…` : "—");
        const directOn = Number(n?.usersOnline ?? n?.users_online ?? n?.onlineUsers);
        const onlineInit = Number.isFinite(directOn) ? directOn : null;
        return {
          label,
          value: total > 0 ? fmtTrafficBytes(total) : fmtTrafficBytes(0),
          sort: total,
          uuid: uuid || null,
          online: onlineInit,
        };
      });
      return { seven: rows.sort((a, b) => b.sort - a.sort) };
    }
    const series = nb.series;
    if (Array.isArray(series) && series.length) {
      const rows = series.map((s) => {
        const total = Number(s?.total ?? 0);
        const uuid = bandwidthRowUuid(s);
        const label =
          (typeof s?.name === "string" && s.name.trim()) ||
          (typeof s?.nodeName === "string" && s.nodeName.trim()) ||
          (uuid ? `${uuid.slice(0, 8)}…` : "—");
        const directOn = Number(s?.usersOnline ?? s?.users_online ?? s?.onlineUsers);
        const onlineInit = Number.isFinite(directOn) ? directOn : null;
        return {
          label,
          value: total > 0 ? fmtTrafficBytes(total) : fmtTrafficBytes(0),
          sort: total,
          uuid: uuid || null,
          online: onlineInit,
        };
      });
      return { seven: rows.sort((a, b) => b.sort - a.sort) };
    }
    return null;
  }

  function parsePanelNodeTraffic(panel) {
    const onlineLookup = buildNodeOnlineLookup(panel);
    const fromBw = parseNodesBandwidthTop(panel);
    if (fromBw?.seven?.length) return { seven: attachNodeOnlineToRows(fromBw.seven, onlineLookup) };

    const raw = panel?.nodes;
    if (raw == null) return { seven: [] };

    if (Array.isArray(raw)) {
      if (raw.length && isNodeMetricsShape(raw[0])) {
        return { seven: attachNodeOnlineToRows(buildNodeMetricsRows(raw), onlineLookup) };
      }
      return { seven: attachNodeOnlineToRows(aggregatePanelNodeRows(raw), onlineLookup) };
    }

    if (typeof raw === "object") {
      if (Array.isArray(raw.nodes) && raw.nodes.length) {
        return { seven: attachNodeOnlineToRows(buildNodeMetricsRows(raw.nodes), onlineLookup) };
      }
      if (Array.isArray(raw.lastSevenDays) && raw.lastSevenDays.length) {
        return {
          seven: attachNodeOnlineToRows(aggregatePanelNodeRows(raw.lastSevenDays), onlineLookup),
        };
      }
    }

    return { seven: [] };
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
    const tail14 = n >= 14 ? amounts.slice(-14) : amounts;
    const total14 = tail14.reduce((a, b) => a + b, 0);
    const maxY = amounts.length ? Math.max(...amounts, 1e-9) : 1e-9;
    return { last7, prev7, growthPct, avgToday, total14, maxY, amounts, n };
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
        <span
          class="admin-skeleton admin-skeleton-line admin-skeleton-line-tiny"
          style="width:30%;margin-top:8px"
        ></span>
      </Card.Header>
      <Card.Content class="admin-cn-card-content--flush">
        <AdminTableSkeleton
          headers={recentPaymentHeaders}
          rows={5}
          widths={["48px", "120px", "78px", "82px", "72px", "96px"]}
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
                    on:click={() => setRevenuePresetDays(d)}
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
                on:click={() => setRevenueGranularity(g)}
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
        <Card.Description
          >{at(
            "stats_records_count",
            { count: (stats.recent_payments || []).length },
            ""
          )}</Card.Description
        >
      </Card.Header>
      <Card.Content class="admin-cn-card-content--flush">
        <div class="admin-table-wrap">
          {#if statsLoading}
            <AdminTableSkeleton
              headers={recentPaymentHeaders}
              rows={5}
              widths={["48px", "120px", "78px", "82px", "72px", "96px"]}
            />
          {:else if recentPaymentsTable.rows.length}
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
                {#each recentPaymentsTable.rows as p (p.payment_id)}
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
            {#if recentPaymentsTotal > RECENT_PAYMENTS_PAGE_SIZE}
              <AdminPagination
                table={recentPaymentsTable}
                pageLabel={at("page_short", {}, "Стр.")}
                ofLabel={at("pagination_of", {}, "из")}
                totalLabel={at("total", {}, "Всего")}
                jumpLabel={at("page_short", {}, "Стр.")}
                jumpAriaLabel={at("pagination_jump_aria", {}, "Перейти к странице")}
                goLabel={at("pagination_go", {}, "Перейти")}
                prevLabel={at("back", {}, "Назад")}
                nextLabel={at("next", {}, "Далее")}
              />
            {/if}
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
