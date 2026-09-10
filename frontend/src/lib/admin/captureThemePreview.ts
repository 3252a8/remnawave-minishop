import { toBlob } from "html-to-image";

const PREVIEW_WIDTH = 1280;
const PREVIEW_HEIGHT = 800;
const PREVIEW_TIMEOUT = 15_000;
const LAYOUT_SETTLE_DELAY = 50;

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function waitForStylesheets(doc: Document): Promise<void> {
  const links = Array.from(doc.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]'));
  await Promise.all(
    links.map(
      (link) =>
        new Promise<void>((resolve, reject) => {
          if (link.sheet) {
            resolve();
            return;
          }
          link.addEventListener("load", () => resolve(), { once: true });
          link.addEventListener("error", () => reject(new Error("preview_stylesheet_failed")), {
            once: true,
          });
        })
    )
  );
}

async function waitForAnimationFrames(doc: Document): Promise<void> {
  const requestFrame = doc.defaultView?.requestAnimationFrame;
  if (!requestFrame) {
    await wait(32);
    return;
  }
  await new Promise<void>((resolve) => requestFrame(() => requestFrame(() => resolve())));
}

async function waitForImages(doc: Document): Promise<void> {
  await Promise.all(
    Array.from(doc.images).map(async (image) => {
      if (!image.complete) {
        await new Promise<void>((resolve, reject) => {
          image.addEventListener("load", () => resolve(), { once: true });
          image.addEventListener("error", () => reject(new Error("preview_image_failed")), {
            once: true,
          });
        });
      }
      if (typeof image.decode === "function") await image.decode();
    })
  );
}

export async function waitForPreviewReady(doc: Document): Promise<void> {
  const deadline = Date.now() + PREVIEW_TIMEOUT;
  while (doc.readyState !== "complete" || !doc.querySelector(".app-shell")) {
    if (Date.now() >= deadline) throw new Error("preview_load_failed");
    await wait(50);
  }
  await waitForStylesheets(doc);
  await waitForImages(doc);
  await doc.fonts.ready;
  await waitForAnimationFrames(doc);
  await wait(LAYOUT_SETTLE_DELAY);
}

export async function captureThemePreview(url: string): Promise<Blob> {
  const iframe = document.createElement("iframe");
  iframe.src = url;
  iframe.width = String(PREVIEW_WIDTH);
  iframe.height = String(PREVIEW_HEIGHT);
  iframe.setAttribute("aria-hidden", "true");
  Object.assign(iframe.style, {
    position: "fixed",
    left: "-10000px",
    top: "0",
    width: `${PREVIEW_WIDTH}px`,
    height: `${PREVIEW_HEIGHT}px`,
    border: "0",
    opacity: "0.01",
    pointerEvents: "none",
  });
  document.body.appendChild(iframe);
  try {
    await new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(() => reject(new Error("preview_load_failed")), PREVIEW_TIMEOUT);
      iframe.addEventListener(
        "load",
        () => {
          window.clearTimeout(timeout);
          resolve();
        },
        { once: true }
      );
      iframe.addEventListener(
        "error",
        () => {
          window.clearTimeout(timeout);
          reject(new Error("preview_load_failed"));
        },
        { once: true }
      );
    });
    const previewDocument = iframe.contentDocument;
    if (!previewDocument) throw new Error("preview_load_failed");
    await waitForPreviewReady(previewDocument);
    const shell = previewDocument.querySelector<HTMLElement>(".app-shell");
    if (!shell) throw new Error("preview_load_failed");
    const blob = await toBlob(shell, {
      width: PREVIEW_WIDTH,
      height: PREVIEW_HEIGHT,
      canvasWidth: PREVIEW_WIDTH,
      canvasHeight: PREVIEW_HEIGHT,
      pixelRatio: 1,
    });
    if (!blob) throw new Error("preview_capture_failed");
    return blob;
  } finally {
    iframe.remove();
  }
}
