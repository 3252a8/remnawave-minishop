import { describe, expect, it } from "vitest";

import {
  aggregateRevenueSeries,
  filterDailyByIsoRange,
  inclusiveDaySpan,
  sliceLastDays,
  utcMonthStartMs,
  utcWeekStartMs,
} from "./revenueSeriesAgg.js";

describe("revenueSeriesAgg", () => {
  const daily = [
    { date: "2026-06-01", amount: 10 },
    { date: "2026-06-07", amount: 5 },
    { date: "2026-06-08", amount: 7 },
    { date: "2026-07-01", amount: 3 },
  ];

  it("filters and slices daily ranges without mutating points", () => {
    expect(filterDailyByIsoRange(daily, "2026-06-07", "2026-06-30")).toEqual([
      { date: "2026-06-07", amount: 5 },
      { date: "2026-06-08", amount: 7 },
    ]);
    expect(sliceLastDays(daily, 2)).toEqual([
      { date: "2026-06-08", amount: 7 },
      { date: "2026-07-01", amount: 3 },
    ]);
    expect(sliceLastDays(daily, 0)).toEqual([]);
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
  });

  it("normalizes invalid amounts and reports inclusive spans", () => {
    expect(
      aggregateRevenueSeries(
        [
          { date: "2026-06-01", amount: "12" },
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

  it("computes UTC bucket starts", () => {
    expect(new Date(utcWeekStartMs("2026-06-07")).toISOString()).toBe("2026-06-01T00:00:00.000Z");
    expect(new Date(utcMonthStartMs("2026-06-30T23:30:00Z")).toISOString()).toBe(
      "2026-06-01T00:00:00.000Z"
    );
  });
});
