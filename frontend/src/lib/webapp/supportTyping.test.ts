import { afterEach, describe, expect, it, vi } from "vitest";

import { createSupportTypingHeartbeat } from "./supportTyping.js";

afterEach(() => {
  vi.useRealTimers();
});

describe("support typing heartbeat", () => {
  it("throttles keypresses and stops after idle time", async () => {
    vi.useFakeTimers();
    const send = vi.fn().mockResolvedValue(undefined);
    const typing = createSupportTypingHeartbeat({ send, heartbeatMs: 2_000, idleMs: 5_000 });

    typing.pulse(42);
    typing.pulse(42);
    typing.pulse(42);
    await vi.advanceTimersByTimeAsync(0);
    expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenLastCalledWith(42, true);

    await vi.advanceTimersByTimeAsync(4_000);
    expect(send).toHaveBeenCalledTimes(3);
    expect(send).toHaveBeenLastCalledWith(42, true);

    await vi.advanceTimersByTimeAsync(1_000);
    expect(send).toHaveBeenLastCalledWith(42, false);
    await vi.advanceTimersByTimeAsync(5_000);
    expect(send).toHaveBeenCalledTimes(4);
  });

  it("stops the previous ticket before starting another", async () => {
    const send = vi.fn().mockResolvedValue(undefined);
    const typing = createSupportTypingHeartbeat({ send });

    typing.pulse(7);
    typing.pulse(8);
    await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(3));

    expect(send.mock.calls).toEqual([
      [7, true],
      [7, false],
      [8, true],
    ]);
    typing.stop();
  });
});
