import { describe, expect, it, vi } from "vitest";

import { createPaymentResponseHandler } from "./billingPaymentResume.js";

describe("createPaymentResponseHandler", () => {
  it("opens a pending provider payment through the payment link action", async () => {
    const openExternalLink = vi.fn();
    const startPaymentStatusPolling = vi.fn();
    const handlePaymentResponse = createPaymentResponseHandler({
      notifyOpened: vi.fn(),
      openExternalLink,
      openQaPaymentLink: vi.fn(),
      openTelegramInvoice: vi.fn(),
      startPaymentStatusPolling,
    });

    const paymentUrl = "https://bank.example.test/pay?id=123";
    await handlePaymentResponse({ ok: true, payment_id: "123", payment_url: paymentUrl });

    expect(openExternalLink).toHaveBeenCalledWith(paymentUrl, "payment");
    expect(startPaymentStatusPolling).toHaveBeenCalledWith("123", {});
  });

  it("keeps checkout open until Telegram returns control from the invoice", async () => {
    let finishInvoice = (_opened: boolean): void => {
      throw new Error("invoice resolver was not initialized");
    };
    const closeModal = vi.fn();
    const startPaymentStatusPolling = vi.fn();
    const afterOpened = vi.fn();
    const handlePaymentResponse = createPaymentResponseHandler({
      afterOpened,
      notifyOpened: vi.fn(),
      openExternalLink: vi.fn(),
      openQaPaymentLink: vi.fn(),
      openTelegramInvoice: vi.fn(
        () =>
          new Promise<boolean>((resolve) => {
            finishInvoice = resolve;
          })
      ),
      startPaymentStatusPolling,
    });

    const handled = handlePaymentResponse(
      {
        ok: true,
        action: "open_invoice",
        payment_id: "stars-1",
        payment_url: "https://t.me/$invoice",
      },
      {},
      closeModal
    );

    await Promise.resolve();
    expect(closeModal).not.toHaveBeenCalled();
    expect(startPaymentStatusPolling).not.toHaveBeenCalled();

    finishInvoice(true);
    await expect(handled).resolves.toBe(true);

    expect(startPaymentStatusPolling).toHaveBeenCalledWith("stars-1", {});
    expect(closeModal).toHaveBeenCalledOnce();
    expect(afterOpened).toHaveBeenCalledOnce();
  });
});
