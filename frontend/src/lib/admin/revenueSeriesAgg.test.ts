import { describe, expect, it } from "vitest";

import {
  aggregateRevenueSeries,
  filterDailyByIsoRange,
  filterRevenueByPreset,
  hasChartValues,
  inclusiveDaySpan,
  isRevenueGranularity,
  isRevenuePreset,
  utcMonthStartMs,
  utcWeekStartMs,
  utcYearStartMs,
} from "./revenueSeriesAgg.js";

describe("revenueSeriesAgg", () => {
  const daily = [
    { date: "2026-06-01", amount: 10 },
    { date: "2026-06-07", amount: 5 },
    { date: "2026-06-08", amount: 7 },
    { date: "2026-07-01", amount: 3 },
  ];

  it("filters daily ISO ranges without mutating points", () => {
    expect(filterDailyByIsoRange(daily, "2026-06-07", "2026-06-30")).toEqual([
      { date: "2026-06-07", amount: 5 },
      { date: "2026-06-08", amount: 7 },
    ]);
  });

  it("buckets revenue by UTC calendar week and month", () => {
    expect(aggregateRevenueSeries(daily, "week")).toEqual([
      { date: "2026-06-01", amount: 15 },
      { date: "2026-06-08", amount: 7 },
      { date: "2026-06-29", amount: 3 },
    ]);
    expect(aggregateRevenueSeries(daily, "month")).toEqual([
      { date: "2026-06-01", amount: 22 },
      { date: "2026-07-01", amount: 3 },
    ]);
    expect(aggregateRevenueSeries(daily, "year")).toEqual([{ date: "2026-01-01", amount: 25 }]);
  });

  it("filters sparse series by calendar presets and preserves all-time data", () => {
    expect(filterRevenueByPreset(daily, 7, "2026-07-01")).toEqual([
      { date: "2026-07-01", amount: 3 },
    ]);
    expect(filterRevenueByPreset(daily, 30, "2026-07-01")).toEqual([
      { date: "2026-06-07", amount: 5 },
      { date: "2026-06-08", amount: 7 },
      { date: "2026-07-01", amount: 3 },
    ]);
    expect(filterRevenueByPreset(daily, "all", "2026-07-01")).toEqual(daily);
    expect(isRevenuePreset("all")).toBe(true);
    expect(isRevenuePreset(1095)).toBe(true);
    expect(isRevenuePreset(1096)).toBe(false);
    expect(isRevenueGranularity("year")).toBe(true);
    expect(isRevenueGranularity("quarter")).toBe(false);
  });

  it("keeps fees aligned with the selected calendar buckets", () => {
    const withFees = [
      { date: "2026-06-01", amount: 100, fees: 3.5 },
      { date: "2026-06-07", amount: 200, fees: 8.25 },
      { date: "2026-06-08", amount: 70, fees: 0 },
    ];
    expect(aggregateRevenueSeries(withFees, "day")).toEqual(withFees);
    expect(aggregateRevenueSeries(withFees, "week")).toEqual([
      { date: "2026-06-01", amount: 300, fees: 11.75 },
      { date: "2026-06-08", amount: 70, fees: 0 },
    ]);
    expect(aggregateRevenueSeries(withFees, "month")).toEqual([
      { date: "2026-06-01", amount: 370, fees: 11.75 },
    ]);
  });

  it("normalizes invalid amounts and reports inclusive spans", () => {
    expect(
      aggregateRevenueSeries(
        [
          { date: "2026-06-01", amount: "12" as unknown as number },
          { date: "2026-06-02", amount: Number.NaN },
        ],
        "day"
      )
    ).toEqual([
      { date: "2026-06-01", amount: 12 },
      { date: "2026-06-02", amount: 0 },
    ]);
    expect(inclusiveDaySpan("2026-06-01", "2026-06-03")).toBe(3);
    expect(inclusiveDaySpan("", "2026-06-03")).toBe(0);
  });

  it("distinguishes calendar buckets from actual chart values", () => {
    expect(hasChartValues([])).toBe(false);
    expect(
      hasChartValues([
        { date: "2026-06-01", amount: 0 },
        { date: "2026-06-02", amount: Number.NaN },
      ])
    ).toBe(false);
    expect(hasChartValues([{ date: "2026-06-01", amount: 0.01 }])).toBe(true);
    expect(hasChartValues([{ date: "2026-06-01", amount: -5 }])).toBe(true);
  });

  it("computes UTC bucket starts", () => {
    expect(new Date(utcWeekStartMs("2026-06-07")).toISOString()).toBe("2026-06-01T00:00:00.000Z");
    expect(new Date(utcMonthStartMs("2026-06-30T23:30:00Z")).toISOString()).toBe(
      "2026-06-01T00:00:00.000Z"
    );
    expect(new Date(utcYearStartMs("2026-12-31T23:30:00Z")).toISOString()).toBe(
      "2026-01-01T00:00:00.000Z"
    );
  });
});
