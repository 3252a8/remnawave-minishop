import QRCode from "qrcode";

export const QR_IMAGE_OPTIONS = {
  errorCorrectionLevel: "M",
  margin: 2,
  width: 640,
  color: { dark: "#000000", light: "#ffffff" },
} as const;

export async function createQrImage(value: string): Promise<string> {
  return value.trim() ? QRCode.toDataURL(value, QR_IMAGE_OPTIONS) : "";
}

export function qrImageBlob(dataUrl: string): Blob {
  const encoded = dataUrl.match(/^data:image\/png;base64,(.+)$/)?.[1];
  if (!encoded) throw new Error("invalid_qr_image");
  const bytes = Uint8Array.from(atob(encoded), (character) => character.charCodeAt(0));
  return new Blob([bytes], { type: "image/png" });
}

export async function copyQrImage(dataUrl: string): Promise<void> {
  if (
    !globalThis.isSecureContext ||
    typeof navigator.clipboard?.write !== "function" ||
    typeof ClipboardItem === "undefined"
  ) {
    throw new Error("image_clipboard_unavailable");
  }
  await navigator.clipboard.write([new ClipboardItem({ "image/png": qrImageBlob(dataUrl) })]);
}

/** File sharing lets supported mobile WebViews save the PNG via their native sheet. */
export async function downloadQrImage(dataUrl: string, filename = "qr-code.png"): Promise<void> {
  const file = new File([qrImageBlob(dataUrl)], filename, { type: "image/png" });
  const inTelegram = Boolean(
    (window as Window & { Telegram?: { WebApp?: { initData?: string } } }).Telegram?.WebApp
      ?.initData
  );
  if (inTelegram && navigator.canShare?.({ files: [file] }) && navigator.share) {
    try {
      await navigator.share({ files: [file] });
      return;
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") throw error;
      // A denied native sheet still leaves the regular browser download available.
    }
  }
  const url = URL.createObjectURL(file);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
