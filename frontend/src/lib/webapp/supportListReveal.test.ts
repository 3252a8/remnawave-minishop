import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createSupportListReveal } from "./supportListReveal.js";

describe("support list reveal", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the empty state instead of skeletons when the filter is known to be empty", () => {
    const reveal = createSupportListReveal();

    expect(reveal.sync({ expectedCount: 0, resolved: false })).toEqual({
      phase: "content",
      skeletonCount: 0,
    });

    vi.advanceTimersByTime(5_000);
    expect(reveal.state.phase).toBe("content");
  });

  it("stays quiet until the request is slow enough to explain", () => {
    const reveal = createSupportListReveal({ probeDelayMs: 220 });

    expect(reveal.sync({ expectedCount: 3, resolved: false }).phase).toBe("pending");

    vi.advanceTimersByTime(219);
    expect(reveal.state.phase).toBe("pending");

    vi.advanceTimersByTime(1);
    expect(reveal.state).toEqual({ phase: "skeleton", skeletonCount: 3 });
  });

  it("never flashes a skeleton for a response that beats the probe delay", () => {
    const reveal = createSupportListReveal({ probeDelayMs: 220 });

    reveal.sync({ expectedCount: 4, resolved: false });
    vi.advanceTimersByTime(100);
    reveal.sync({ expectedCount: 4, resolved: true });

    expect(reveal.state.phase).toBe("content");
    vi.advanceTimersByTime(1_000);
    expect(reveal.state.phase).toBe("content");
  });

  it("sizes skeletons to the expected ticket count", () => {
    const reveal = createSupportListReveal({ maxSkeletonCount: 5, probeDelayMs: 220 });

    reveal.sync({ expectedCount: 2, resolved: false });
    vi.advanceTimersByTime(220);
    expect(reveal.state).toEqual({ phase: "skeleton", skeletonCount: 2 });

    reveal.sync({ expectedCount: 40, resolved: false });
    expect(reveal.state.skeletonCount).toBe(5);
  });

  it("falls back to the default skeleton count while the count is unknown", () => {
    const reveal = createSupportListReveal({ defaultSkeletonCount: 3, probeDelayMs: 220 });

    reveal.sync({ expectedCount: null, resolved: false });
    vi.advanceTimersByTime(220);

    expect(reveal.state).toEqual({ phase: "skeleton", skeletonCount: 3 });
  });

  it("holds the probe deadline across mid-flight count updates", () => {
    const reveal = createSupportListReveal({ probeDelayMs: 220 });

    reveal.sync({ expectedCount: null, resolved: false });
    vi.advanceTimersByTime(200);
    reveal.sync({ expectedCount: 2, resolved: false });

    vi.advanceTimersByTime(20);
    expect(reveal.state).toEqual({ phase: "skeleton", skeletonCount: 2 });
  });

  it("keeps shown skeletons on screen long enough to read", () => {
    const reveal = createSupportListReveal({ minSkeletonMs: 320, probeDelayMs: 220 });

    reveal.sync({ expectedCount: 3, resolved: false });
    vi.advanceTimersByTime(220);
    expect(reveal.state.phase).toBe("skeleton");

    vi.advanceTimersByTime(100);
    reveal.sync({ expectedCount: 3, resolved: true });
    expect(reveal.state.phase).toBe("skeleton");

    vi.advanceTimersByTime(219);
    expect(reveal.state.phase).toBe("skeleton");

    vi.advanceTimersByTime(1);
    expect(reveal.state.phase).toBe("content");
  });

  it("falls back to content when the request never resolves", () => {
    const reveal = createSupportListReveal({ failsafeMs: 8_000, probeDelayMs: 220 });

    reveal.sync({ expectedCount: 2, resolved: false });
    vi.advanceTimersByTime(220);
    expect(reveal.state.phase).toBe("skeleton");

    vi.advanceTimersByTime(8_000);
    expect(reveal.state.phase).toBe("content");
  });

  it("waits again when the user switches to another populated filter", () => {
    const onChange = vi.fn();
    const reveal = createSupportListReveal({ onChange, probeDelayMs: 220 });

    reveal.sync({ expectedCount: 1, resolved: true });
    expect(reveal.state.phase).toBe("content");

    expect(reveal.sync({ expectedCount: 4, resolved: false }).phase).toBe("pending");
    vi.advanceTimersByTime(220);
    expect(onChange).toHaveBeenLastCalledWith({ phase: "skeleton", skeletonCount: 4 });
  });

  it("stops pending work once destroyed", () => {
    const onChange = vi.fn();
    const reveal = createSupportListReveal({ onChange, probeDelayMs: 220 });

    reveal.sync({ expectedCount: 2, resolved: false });
    reveal.destroy();
    vi.advanceTimersByTime(5_000);

    expect(reveal.state.phase).toBe("pending");
    expect(onChange).not.toHaveBeenCalled();
  });
});
