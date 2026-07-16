import { describe, expect, it } from "vitest";

import {
  computeRevenueKpis,
  formatTrafficGbCell,
  growthBadgeVariant,
  parsePanelBandwidth,
  parsePanelNodeTraffic,
  parsePanelSystem,
  paymentDescriptionDisplay,
} from "./statsDerivations";

describe("statsDerivations", () => {
  const at = (key: string, params: Record<string, unknown> = {}, fallback = key) =>
    `${fallback}:${JSON.stringify(params)}`;

  it("derives panel system and bandwidth metrics from mixed panel payloads", () => {
    expect(
      parsePanelSystem({
        system: {
          users: { statusCounts: { ACTIVE: 10, DISABLED: 1 }, totalUsers: 14 },
          onlineStats: { onlineNow: 3 },
          memory: { total: 100, used: 25 },
          cpu: { usedPercent: "12.5" },
        },
      })
    ).toEqual({
      onlineNow: 3,
      active: 10,
      disabled: 1,
      expired: 0,
      limited: 0,
      totalPanelUsers: 14,
      memPct: 25,
      cpuPct: 12.5,
    });

    expect(
      parsePanelBandwidth({
        bandwidth: {
          bandwidthLastSevenDays: { current: "7d" },
          bandwidthLastThirtyDays: { current: "30d" },
        },
      })
    ).toEqual({ week: "7d", month: "30d" });
  });

  it("normalizes node traffic rows and attaches online counts", () => {
    expect(
      parsePanelNodeTraffic({
        nodes: [
          { uuid: "node-1", name: "Alpha", usersOnline: 4 },
          { uuid: "node-2", name: "Beta", usersOnline: 1 },
        ],
        nodes_bandwidth: {
          topNodes: [
            { uuid: "node-2", name: "Beta", total: 2 * 1024 ** 3 },
            { uuid: "node-1", name: "Alpha", total: 3 * 1024 ** 3 },
          ],
        },
      }).seven
    ).toEqual([
      { label: "Alpha", value: "3 GB", sort: 3 * 1024 ** 3, uuid: "node-1", online: 4 },
      { label: "Beta", value: "2 GB", sort: 2 * 1024 ** 3, uuid: "node-2", online: 1 },
    ]);
  });

  it("computes revenue KPI windows and badge variants", () => {
    const series = Array.from({ length: 14 }, (_, index) => ({
      date: `2026-06-${String(index + 1).padStart(2, "0")}`,
      amount: index + 1,
    }));

    expect(
      computeRevenueKpis({ today_payments_count: 2, today_revenue: 50 }, series)
    ).toMatchObject({
      last7: 77,
      prev7: 28,
      growthPct: 175,
      avgToday: 25,
      total14: 105,
      n: 14,
    });
    expect(growthBadgeVariant(1)).toBe("default");
    expect(growthBadgeVariant(-1)).toBe("destructive");
    expect(growthBadgeVariant(null)).toBe("outline");
  });

  it("formats payment traffic descriptions and GB cells", () => {
    expect(formatTrafficGbCell(12.345)).toBe("12.35 GB");
    expect(formatTrafficGbCell("")).toBe("—");
    expect(
      paymentDescriptionDisplay({ traffic_regular_gb: 10, description: "" } as never, at)
    ).toBe('Traffic package {gb} GB (standard):{"gb":"10"}');
    expect(paymentDescriptionDisplay({ description: "Manual" } as never, at)).toBe("Manual");
  });
});
