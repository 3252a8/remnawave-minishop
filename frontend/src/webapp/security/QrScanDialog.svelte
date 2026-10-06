<script lang="ts">
  /**
   * Scans a sign-in QR code with the page's own camera, for sessions that cannot
   * use Telegram's scanner (a browser, or Telegram Desktop). Uses the built-in
   * BarcodeDetector where the browser has one and a small decoder otherwise.
   */
  import { untrack } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";
  import { parseQrLoginCode } from "$lib/webapp/qrLogin.js";

  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type Props = {
    open?: boolean;
    t: Translate;
    hint?: string;
    onscan: (code: string) => void;
    onclose: () => void;
  };
  type Problem = "" | "starting" | "denied" | "unavailable" | "not_login_code";
  type Decode = (frame: HTMLVideoElement) => Promise<string | null>;
  type BarcodeDetectorLike = {
    detect: (source: HTMLVideoElement) => Promise<{ rawValue?: string }[]>;
  };
  type BarcodeDetectorClass = {
    new (options: { formats: string[] }): BarcodeDetectorLike;
    getSupportedFormats?: () => Promise<string[]>;
  };

  let { open = false, t, hint = "", onscan, onclose }: Props = $props();

  const SCAN_EVERY_MS = 250;

  let video = $state<HTMLVideoElement | null>(null);
  let problem = $state<Problem>("starting");
  let stream: MediaStream | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let active = false;

  async function nativeDecoder(): Promise<Decode | null> {
    const Detector = (globalThis as unknown as { BarcodeDetector?: BarcodeDetectorClass })
      .BarcodeDetector;
    if (!Detector) return null;
    try {
      const formats = (await Detector.getSupportedFormats?.()) ?? ["qr_code"];
      if (!formats.includes("qr_code")) return null;
      const detector = new Detector({ formats: ["qr_code"] });
      return async (frame) => (await detector.detect(frame))[0]?.rawValue || null;
    } catch {
      return null;
    }
  }

  async function scriptDecoder(): Promise<Decode> {
    const { default: jsQR } = await import("jsqr");
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d", { willReadFrequently: true });
    return async (frame) => {
      const width = frame.videoWidth;
      const height = frame.videoHeight;
      if (!context || !width || !height) return null;
      canvas.width = width;
      canvas.height = height;
      context.drawImage(frame, 0, 0, width, height);
      const image = context.getImageData(0, 0, width, height);
      return jsQR(image.data, width, height, { inversionAttempts: "dontInvert" })?.data || null;
    };
  }

  function stop(): void {
    active = false;
    if (timer) clearTimeout(timer);
    timer = null;
    for (const track of stream?.getTracks() ?? []) track.stop();
    stream = null;
  }

  async function start(element: HTMLVideoElement): Promise<void> {
    problem = "starting";
    if (!navigator.mediaDevices?.getUserMedia) {
      problem = "unavailable";
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
    } catch (error) {
      problem =
        (error as { name?: string } | null)?.name === "NotAllowedError" ? "denied" : "unavailable";
      return;
    }
    if (!active) {
      stop();
      return;
    }
    element.srcObject = stream;
    await element.play().catch(() => undefined);
    problem = "";
    const decode = (await nativeDecoder()) ?? (await scriptDecoder());
    const tick = async (): Promise<void> => {
      if (!active) return;
      const text = element.readyState >= 2 ? await decode(element).catch(() => null) : null;
      if (!active) return;
      if (text) {
        const code = parseQrLoginCode(text);
        if (code) {
          stop();
          onscan(code);
          return;
        }
        problem = "not_login_code";
      }
      timer = setTimeout(() => void tick(), SCAN_EVERY_MS);
    };
    void tick();
  }

  $effect(() => {
    const element = video;
    if (!open || !element) return;
    active = true;
    untrack(() => void start(element));
    return () => stop();
  });

  function close(): void {
    stop();
    onclose();
  }
</script>

<Dialog
  {open}
  title={t("wa_qr_scan_title")}
  description={hint || t("wa_qr_scan_hint")}
  closeLabel={t("wa_close")}
  onclose={close}
  class="qr-scan-dialog"
>
  <div class="qr-scan">
    <div class="qr-scan-viewport">
      <video bind:this={video} playsinline muted autoplay></video>
      <span class="qr-scan-frame" aria-hidden="true"></span>
    </div>
    {#if problem === "starting"}
      <StatusMessage>{t("wa_qr_scan_starting")}</StatusMessage>
    {:else if problem === "denied"}
      <StatusMessage error>{t("wa_qr_scan_camera_denied")}</StatusMessage>
    {:else if problem === "unavailable"}
      <StatusMessage error>{t("wa_qr_scan_unavailable")}</StatusMessage>
    {:else if problem === "not_login_code"}
      <StatusMessage error>{t("wa_qr_scan_not_login_code")}</StatusMessage>
    {/if}
  </div>
</Dialog>

<style>
  .qr-scan {
    display: grid;
    justify-items: center;
    gap: 12px;
    min-width: 0;
  }
  .qr-scan-viewport {
    position: relative;
    width: min(100%, 320px);
    aspect-ratio: 1;
    overflow: hidden;
    border-radius: var(--radius-card);
    background: #000000;
  }
  .qr-scan-viewport video {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .qr-scan-frame {
    position: absolute;
    inset: 16%;
    border: 3px solid rgb(255 255 255 / 0.9);
    border-radius: var(--radius-inner);
    box-shadow: 0 0 0 999px rgb(0 0 0 / 0.35);
    pointer-events: none;
  }
</style>
