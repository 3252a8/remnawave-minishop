import { fmtTrafficBytes } from "./format.js";
import type { PaymentOut } from "./stores/paymentsStore";
import type { StatsState } from "./stores/statsStore";

export type BadgeVariant = "default" | "outline" | "destructive" | "success" | "muted";
export type RevenuePoint = { date: string; amount: number };
export type DynamicRecord = Record<string, unknown>;
export type PanelStats = DynamicRecord & {
  error?: unknown;
  system?: DynamicRecord & {
    users?: DynamicRecord & { statusCounts?: DynamicRecord; totalUsers?: unknown };
    onlineStats?: DynamicRecord & { onlineNow?: unknown };
    memory?: DynamicRecord & { total?: unknown; used?: unknown };
    cpu?: DynamicRecord & {
      usage?: unknown;
      usedPercent?: unknown;
      percent?: unknown;
    };
    cpuUsage?: unknown;
    cpuLoad?: unknown;
  };
  bandwidth?: DynamicRecord & {
    bandwidthLastSevenDays?: DynamicRecord & { current?: unknown };
    bandwidthLast30Days?: DynamicRecord & { current?: unknown };
    bandwidthLastThirtyDays?: DynamicRecord & { current?: unknown };
  };
  nodes?: unknown;
  nodes_bandwidth?: DynamicRecord & { topNodes?: unknown; series?: unknown };
};
export type PanelMetricRow = DynamicRecord & {
  label: string;
  value: string;
  sort: number;
  uuid: string | null;
  online: number | null;
};
export type PanelNodeTraffic = { seven: PanelMetricRow[] };
export type PanelSystemMetrics = {
  onlineNow: unknown;
  active: unknown;
  disabled: unknown;
  expired: unknown;
  limited: unknown;
  totalPanelUsers: unknown;
  memPct: number | null;
  cpuPct: number | null;
};
export type AdminStats = NonNullable<StatsState["stats"]> & {
  financial: DynamicRecord & {
    daily_series?: RevenuePoint[];
    today_payments_count?: unknown;
    today_revenue?: unknown;
    week_revenue?: unknown;
    month_revenue?: unknown;
    all_time_revenue?: unknown;
  };
  panel: PanelStats | null;
  recent_payments: PaymentOut[];
  users: DynamicRecord & {
    total_users?: number;
    active_today?: number;
    banned_users?: number;
    referral_users?: number;
    active_subscriptions?: number;
    paid_subscriptions?: number;
    free_subscription_users?: number;
    trial_users?: number;
    inactive_users?: number;
    expired_subscription_users?: number;
  };
};
export type RevenueKpis = {
  last7: number;
  prev7: number;
  growthPct: number | null;
  avgToday: number | null;
  total14: number;
  maxY: number;
  amounts: number[];
  n: number;
};
export type CustomRangeApply = { fromIso: string; toIso: string };

type NodeLookup = { byUuid: Map<string, number>; byName: Map<string, number> };
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

export function isRecord(value: unknown): value is DynamicRecord {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function recordRows(value: unknown): DynamicRecord[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

export function formatTrafficGbCell(v: number | string | null | undefined): string {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  let s;
  if (Math.abs(n - Math.round(n)) < 1e-9) {
    s = String(Math.round(n));
  } else {
    s = String(Math.round(n * 100) / 100);
  }
  return `${s} GB`;
}

function formatGbAmountPlain(v: number | string | null | undefined): string {
  if (v == null || v === "") return "";
  const n = Number(v);
  if (Number.isNaN(n)) return "";
  if (Math.abs(n - Math.round(n)) < 1e-9) return String(Math.round(n));
  return String(Math.round(n * 100) / 100);
}

export function paymentDescriptionDisplay(p: PaymentOut, t: TranslateFn): string {
  const r = p.traffic_regular_gb;
  const pr = p.traffic_premium_gb;
  if (r != null && pr == null) {
    const gb = formatGbAmountPlain(r);
    return t("payments_desc_traffic_package_regular", { gb }, "Traffic package {gb} GB (standard)");
  }
  if (pr != null && r == null) {
    const gb = formatGbAmountPlain(pr);
    return t("payments_desc_traffic_package_premium", { gb }, "Traffic package {gb} GB (premium)");
  }
  const raw = p.description && String(p.description).trim();
  return raw || "—";
}

export function parsePanelSystem(panel: PanelStats): PanelSystemMetrics | null {
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

export function parsePanelBandwidth(panel: PanelStats): { week: unknown; month: unknown } | null {
  const bw = panel?.bandwidth;
  if (!bw || typeof bw !== "object") return null;
  const week = bw.bandwidthLastSevenDays?.current;
  const month = bw.bandwidthLast30Days?.current ?? bw.bandwidthLastThirtyDays?.current;
  if (week == null && month == null) return null;
  return { week, month };
}

function panelRowBytes(row: DynamicRecord | null | undefined): number {
  if (!row) return 0;
  const total = Number(row.total);
  if (Number.isFinite(total) && total > 0) return total;
  const up = Number(row.uploadBytes ?? row.uplinkBytes ?? row.uplink ?? row.up ?? row.upload);
  const down = Number(
    row.downloadBytes ?? row.downlinkBytes ?? row.downlink ?? row.down ?? row.download
  );
  const sum = (Number.isFinite(up) ? up : 0) + (Number.isFinite(down) ? down : 0);
  return sum > 0 ? sum : 0;
}

function sumDirectionPair(item: DynamicRecord | null | undefined): number {
  if (!item) return 0;
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

function sumTaggedStatsList(arr: unknown): number {
  return recordRows(arr).reduce((acc, item) => acc + sumDirectionPair(item), 0);
}

function trafficBytesFromNodeRecord(node: DynamicRecord | null | undefined): number {
  if (!node) return 0;
  let bytes =
    sumTaggedStatsList(node.inboundsStats) +
    sumTaggedStatsList(node.outboundsStats) +
    sumTaggedStatsList(node.inbounds_stats) +
    sumTaggedStatsList(node.outbounds_stats);
  if (bytes <= 0) bytes = panelRowBytes(node);
  const life = Number(
    node.totalBytesLifetime ?? node.totalBytes ?? node.bytesLifetime ?? node.totalTrafficBytes
  );
  if (bytes <= 0 && Number.isFinite(life) && life > 0) bytes = life;
  return bytes;
}

function isNodeMetricsShape(row: DynamicRecord | null | undefined): boolean {
  if (!row) return false;
  return (
    Array.isArray(row.inboundsStats) ||
    Array.isArray(row.outboundsStats) ||
    Array.isArray(row.inbounds_stats) ||
    Array.isArray(row.outbounds_stats)
  );
}

function panelRowLabel(row: DynamicRecord | null | undefined): string {
  if (!row) return "—";
  for (const key of ["nodeName", "node_name", "name", "nodeRemark", "remark", "label", "title"]) {
    const value = row[key];
    if (value != null && String(value).trim()) return String(value).trim();
  }
  const uuid = row.nodeUuid ?? row.node_uuid ?? row.uuid;
  if (uuid) return `${String(uuid).slice(0, 8)}…`;
  return "—";
}

function nodeRecordUuid(row: DynamicRecord | null | undefined): string {
  if (!row) return "";
  const uuid = row.nodeUuid ?? row.node_uuid ?? row.uuid ?? row.id;
  return uuid != null ? String(uuid) : "";
}

function nodeRecordDisplayName(row: DynamicRecord | null | undefined): string {
  if (!row) return "";
  for (const key of ["nodeName", "node_name", "name", "label", "title", "hostname"]) {
    const value = row[key];
    if (value != null && String(value).trim()) return String(value).trim();
  }
  return "";
}

function nodeRecordUsersOnline(row: DynamicRecord | null | undefined): number | null {
  if (!row) return null;
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
  const metricGroups = row.metricGroups;
  if (isRecord(metricGroups)) {
    const value = Number(metricGroups.onlineUsers ?? metricGroups.online_users);
    if (Number.isFinite(value)) return value;
  }
  return null;
}

function extractPanelNodesList(raw: unknown): DynamicRecord[] {
  if (!raw) return [];
  if (Array.isArray(raw)) return recordRows(raw);
  if (!isRecord(raw)) return [];
  if (Array.isArray(raw.nodes)) return recordRows(raw.nodes);
  if (Array.isArray(raw.items)) return recordRows(raw.items);
  if (Array.isArray(raw.data)) return recordRows(raw.data);
  if (Array.isArray(raw.response)) return recordRows(raw.response);
  return [];
}

function buildNodeOnlineLookup(panel: PanelStats): NodeLookup {
  const byUuid = new Map<string, number>();
  const byName = new Map<string, number>();
  const list = extractPanelNodesList(panel?.nodes);
  for (const node of list) {
    if (!node || typeof node !== "object") continue;
    const online = nodeRecordUsersOnline(node);
    if (online == null) continue;
    const id = nodeRecordUuid(node);
    if (id) byUuid.set(id.toLowerCase(), online);
    const name = nodeRecordDisplayName(node);
    if (name) byName.set(name.toLowerCase(), online);
  }
  return { byUuid, byName };
}

function formatTrafficCell(
  bytes: number,
  row: DynamicRecord | null | undefined,
  stringHint: unknown
): string {
  if (bytes > 0) return fmtTrafficBytes(bytes);
  const current = row?.current;
  if (typeof current === "string" && current.trim()) return current.trim();
  if (typeof stringHint === "string" && stringHint.trim()) return stringHint.trim();
  if (isNodeMetricsShape(row) && !bytes) return fmtTrafficBytes(0);
  return "—";
}

function buildNodeMetricsRows(nodes: DynamicRecord[]): PanelMetricRow[] {
  return nodes
    .filter((node) => node && typeof node === "object")
    .map((node) => {
      const bytes = trafficBytesFromNodeRecord(node);
      const uuid = nodeRecordUuid(node);
      return {
        label: panelRowLabel(node),
        value: formatTrafficCell(bytes, node, ""),
        sort: bytes,
        uuid: uuid || null,
        online: nodeRecordUsersOnline(node),
      };
    })
    .sort((a, b) => b.sort - a.sort);
}

function aggregatePanelNodeRows(rows: unknown): PanelMetricRow[] {
  const sourceRows = recordRows(rows);
  if (!sourceRows.length) return [];
  const map = new Map<string, { label: string; bytes: number; stringHint: string }>();
  for (const row of sourceRows) {
    const key = String(
      row.nodeUuid ?? row.node_uuid ?? row.uuid ?? row.nodeName ?? row.name ?? panelRowLabel(row)
    );
    const prev = map.get(key) || { label: panelRowLabel(row), bytes: 0, stringHint: "" };
    const add = isNodeMetricsShape(row) ? trafficBytesFromNodeRecord(row) : panelRowBytes(row);
    prev.bytes += add;
    const current = row.current;
    if (typeof current === "string" && current.trim()) prev.stringHint = current.trim();
    prev.label = panelRowLabel(row) || prev.label;
    map.set(key, prev);
  }
  return [...map.values()]
    .map((item) => ({
      label: item.label,
      value:
        item.bytes > 0
          ? fmtTrafficBytes(item.bytes)
          : item.stringHint && String(item.stringHint).trim()
            ? String(item.stringHint).trim()
            : "—",
      sort: item.bytes,
      uuid: null,
      online: null,
    }))
    .sort((a, b) => b.sort - a.sort);
}

function bandwidthRowUuid(node: DynamicRecord | null | undefined): string {
  if (!node) return "";
  const uuid = node.uuid ?? node.nodeUuid ?? node.node_uuid ?? node.id;
  return uuid != null ? String(uuid) : "";
}

function attachNodeOnlineToRows(rows: PanelMetricRow[], lookup: NodeLookup): PanelMetricRow[] {
  if (!Array.isArray(rows) || !lookup) return rows;
  const { byUuid, byName } = lookup;
  if (!byUuid.size && !byName.size) return rows;
  return rows.map((row) => {
    let online = row.online;
    if (online == null && row.uuid) {
      const hit = byUuid.get(String(row.uuid).toLowerCase());
      if (hit != null) online = hit;
    }
    if (online == null && row.label && typeof row.label === "string") {
      const hit = byName.get(row.label.trim().toLowerCase());
      if (hit != null) online = hit;
    }
    if (online != null) return { ...row, online };
    return row;
  });
}

function parseNodesBandwidthTop(panel: PanelStats): PanelNodeTraffic | null {
  const bandwidth = panel?.nodes_bandwidth;
  if (!bandwidth || typeof bandwidth !== "object") return null;
  const topRows = recordRows(bandwidth.topNodes);
  if (topRows.length) {
    const rows = topRows.map((node) => {
      const total = Number(node?.total ?? node?.bytes ?? 0);
      const uuid = bandwidthRowUuid(node);
      const label =
        (typeof node?.name === "string" && node.name.trim()) ||
        (typeof node?.nodeName === "string" && node.nodeName.trim()) ||
        (uuid ? `${uuid.slice(0, 8)}…` : "—");
      const directOnline = Number(node?.usersOnline ?? node?.users_online ?? node?.onlineUsers);
      const onlineInit = Number.isFinite(directOnline) ? directOnline : null;
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
  const seriesRows = recordRows(bandwidth.series);
  if (seriesRows.length) {
    const rows = seriesRows.map((series) => {
      const total = Number(series?.total ?? 0);
      const uuid = bandwidthRowUuid(series);
      const label =
        (typeof series?.name === "string" && series.name.trim()) ||
        (typeof series?.nodeName === "string" && series.nodeName.trim()) ||
        (uuid ? `${uuid.slice(0, 8)}…` : "—");
      const directOnline = Number(
        series?.usersOnline ?? series?.users_online ?? series?.onlineUsers
      );
      const onlineInit = Number.isFinite(directOnline) ? directOnline : null;
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

export function parsePanelNodeTraffic(panel: PanelStats): PanelNodeTraffic {
  const onlineLookup = buildNodeOnlineLookup(panel);
  const fromBandwidth = parseNodesBandwidthTop(panel);
  if (fromBandwidth?.seven?.length) {
    return { seven: attachNodeOnlineToRows(fromBandwidth.seven, onlineLookup) };
  }

  const raw = panel?.nodes;
  if (raw == null) return { seven: [] };

  if (Array.isArray(raw)) {
    if (raw.length && isNodeMetricsShape(raw[0])) {
      return { seven: attachNodeOnlineToRows(buildNodeMetricsRows(raw), onlineLookup) };
    }
    return { seven: attachNodeOnlineToRows(aggregatePanelNodeRows(raw), onlineLookup) };
  }

  if (isRecord(raw)) {
    if (Array.isArray(raw.nodes) && raw.nodes.length) {
      return {
        seven: attachNodeOnlineToRows(buildNodeMetricsRows(recordRows(raw.nodes)), onlineLookup),
      };
    }
    if (Array.isArray(raw.lastSevenDays) && raw.lastSevenDays.length) {
      return {
        seven: attachNodeOnlineToRows(aggregatePanelNodeRows(raw.lastSevenDays), onlineLookup),
      };
    }
  }

  return { seven: [] };
}

export function computeRevenueKpis(
  financial: AdminStats["financial"],
  series: RevenuePoint[]
): RevenueKpis {
  const amounts = series.map((point) => Number(point.amount) || 0);
  const n = amounts.length;
  const last7 = n ? amounts.slice(-7).reduce((a, b) => a + b, 0) : 0;
  const prev7 = n > 7 ? amounts.slice(-14, -7).reduce((a, b) => a + b, 0) : 0;
  let growthPct: number | null = null;
  if (n >= 14 && prev7 > 0) growthPct = ((last7 - prev7) / prev7) * 100;
  const todayPaymentsCount = Number(financial.today_payments_count) || 0;
  const todayRevenue = Number(financial.today_revenue) || 0;
  const avgToday = todayPaymentsCount > 0 ? todayRevenue / todayPaymentsCount : null;
  const tail14 = n >= 14 ? amounts.slice(-14) : amounts;
  const total14 = tail14.reduce((a, b) => a + b, 0);
  const maxY = amounts.length ? Math.max(...amounts, 1e-9) : 1e-9;
  return { last7, prev7, growthPct, avgToday, total14, maxY, amounts, n };
}

export function growthBadgeVariant(pct: number | null): BadgeVariant {
  if (pct == null) return "outline";
  if (pct >= 0) return "default";
  return "destructive";
}
