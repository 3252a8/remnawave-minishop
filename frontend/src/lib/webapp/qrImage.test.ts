import { afterEach, describe, expect, it, vi } from "vitest";
import { copyQrImage, createQrImage, downloadQrImage, qrImageBlob } from "./qrImage";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("QR image export", () => {
  it("uses a supported WebView native file sheet", async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("window", { Telegram: { WebApp: { initData: "signed" } } });
    vi.stubGlobal("navigator", { canShare: () => true, share });
    await downloadQrImage("data:image/png;base64,AA==");
    expect(share.mock.calls[0][0].files[0].type).toBe("image/png");
    expect(share.mock.calls[0][0].files[0].name).toBe("qr-code.png");
  });
  it("falls back to browser download if a native sheet rejects permission", async () => {
    vi.useFakeTimers();
    const click = vi.fn();
    const remove = vi.fn();
    const anchor = { click, remove, href: "", download: "" };
    vi.stubGlobal("window", { Telegram: { WebApp: { initData: "signed" } } });
    vi.stubGlobal("navigator", {
      canShare: () => true,
      share: vi.fn().mockRejectedValue(new DOMException("Denied", "NotAllowedError")),
    });
    vi.stubGlobal("document", { createElement: () => anchor, body: { append: vi.fn() } });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:qr-export");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    await downloadQrImage("data:image/png;base64,AA==");
    expect(click).toHaveBeenCalledOnce();
    expect(anchor.download).toBe("qr-code.png");
    await vi.runAllTimersAsync();
    expect(revoke).toHaveBeenCalledWith("blob:qr-export");
  });
  it("creates a PNG and never exports an unavailable link", async () => {
    const image = await createQrImage("https://example.test/gift?token=secret");
    const blob = qrImageBlob(image);
    expect(blob.type).toBe("image/png");
    expect(new Uint8Array(await blob.arrayBuffer()).slice(0, 8)).toEqual(
      new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10])
    );
    expect(await createQrImage("")).toBe("");
  });
  it("rejects unsupported image copying rather than reporting success", async () => {
    vi.stubGlobal("isSecureContext", false);
    vi.stubGlobal("navigator", {});
    await expect(copyQrImage("data:image/png;base64,AA==")).rejects.toThrow(
      "image_clipboard_unavailable"
    );
  });
  it("copies image/png and propagates clipboard permission failures", async () => {
    const write = vi.fn().mockRejectedValue(new DOMException("Denied", "NotAllowedError"));
    vi.stubGlobal("isSecureContext", true);
    vi.stubGlobal("navigator", { clipboard: { write } });
    vi.stubGlobal(
      "ClipboardItem",
      class {
        constructor(public data: Record<string, Blob>) {}
      }
    );
    await expect(copyQrImage("data:image/png;base64,AA==")).rejects.toThrow("Denied");
    expect(write).toHaveBeenCalledOnce();
    expect(write.mock.calls[0][0][0].data["image/png"].type).toBe("image/png");
  });
});
