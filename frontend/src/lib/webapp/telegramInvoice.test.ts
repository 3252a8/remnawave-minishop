import { describe, expect, it, vi } from "vitest";

import { openTelegramInvoice } from "./telegramInvoice.js";

describe("openTelegramInvoice", () => {
  it("does not invoke the Telegram invoice API outside a Mini App", async () => {
    const openInvoice = vi.fn();
    const onUnavailable = vi.fn();

    await expect(
      openTelegramInvoice({
        onFailed: vi.fn(),
        onPaid: vi.fn(),
        onUnavailable,
        telegramSdk: { hasLaunchParams: () => false },
        tg: { openInvoice },
        url: "https://t.me/$invoice",
      })
    ).resolves.toBe(false);

    expect(openInvoice).not.toHaveBeenCalled();
    expect(onUnavailable).toHaveBeenCalledOnce();
  });

  it("loads and opens an invoice inside a Telegram Mini App", async () => {
    const onPaid = vi.fn();
    const openInvoice = vi.fn((_url: string, callback: (status: string) => void) => {
      callback("paid");
    });

    await expect(
      openTelegramInvoice({
        onFailed: vi.fn(),
        onPaid,
        onUnavailable: vi.fn(),
        telegramSdk: {
          ensureForAction: async () => ({ openInvoice }),
          hasLaunchParams: () => true,
        },
        url: "https://t.me/$invoice",
      })
    ).resolves.toBe(true);

    expect(openInvoice).toHaveBeenCalledWith("https://t.me/$invoice", expect.any(Function));
    expect(onPaid).toHaveBeenCalledOnce();
  });
});
