import { describe, expect, it, vi } from "vitest";

import { lazyScreen } from "./lazyScreen.svelte";

describe("lazy screen loading", () => {
  it("reports a failed chunk request and loads the screen on retry", async () => {
    let attempts = 0;
    const screen = lazyScreen(async () => {
      attempts += 1;
      if (attempts === 1) throw new Error("chunk unavailable");
      return { default: "ready" };
    });

    screen.load();
    await vi.waitFor(() => expect(screen.failed).toBe(true));
    expect(screen.component).toBeNull();

    screen.load();
    await vi.waitFor(() => expect(screen.component).toBe("ready"));
    expect(screen.failed).toBe(false);
    expect(attempts).toBe(2);
  });
});
