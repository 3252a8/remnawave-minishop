<script lang="ts">
  /**
   * Shows a link as a QR code for someone else's phone camera to open.
   *
   * The code is always dark on a white tile, whatever the theme: many camera
   * apps cannot read light-on-dark codes, and the person scanning may use any
   * of them.
   */
  import QRCode from "qrcode";
  import Dialog from "$components/ui/dialog.svelte";

  type Props = {
    open?: boolean;
    link?: string;
    title: string;
    description?: string;
    /** Names the link under the code when a screen offers several. */
    caption?: string;
    alt: string;
    closeLabel: string;
    onclose?: () => void;
  };

  let {
    open = false,
    link = "",
    title,
    description = "",
    caption = "",
    alt,
    closeLabel,
    onclose = () => {},
  }: Props = $props();

  const QR_OPTIONS = {
    errorCorrectionLevel: "M",
    margin: 2,
    width: 640,
    color: { dark: "#000000", light: "#ffffff" },
  } as const;

  let qrDataUrl = $state("");

  $effect(() => {
    const value = open ? link.trim() : "";
    qrDataUrl = "";
    if (!value) return;
    let current = true;
    QRCode.toDataURL(value, QR_OPTIONS)
      .then((url: string) => {
        if (current) qrDataUrl = url;
      })
      .catch(() => {
        if (current) qrDataUrl = "";
      });
    return () => {
      current = false;
    };
  });
</script>

<Dialog {open} {title} {description} {closeLabel} {onclose} class="link-qr-dialog">
  <div class="link-qr">
    <div class="link-qr-tile">
      {#if qrDataUrl}
        <img src={qrDataUrl} {alt} />
      {:else}
        <span class="link-qr-placeholder" aria-hidden="true"></span>
      {/if}
    </div>
    {#if caption}<strong class="link-qr-caption">{caption}</strong>{/if}
    <p class="link-qr-value">{link}</p>
  </div>
</Dialog>

<style>
  .link-qr {
    display: grid;
    justify-items: center;
    gap: 10px;
    min-width: 0;
  }
  .link-qr-tile {
    display: grid;
    place-items: center;
    width: min(100%, 280px);
    aspect-ratio: 1;
    padding: 12px;
    border-radius: var(--radius-card);
    background: #ffffff;
  }
  .link-qr-tile img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
    image-rendering: pixelated;
  }
  .link-qr-placeholder {
    display: block;
    width: 100%;
    height: 100%;
    border-radius: var(--radius-inner);
    background: color-mix(in srgb, #000000 6%, #ffffff);
  }
  .link-qr-caption {
    color: var(--text);
    font-size: 13px;
  }
  .link-qr-value {
    max-width: 100%;
    margin: 0;
    color: var(--muted);
    font-size: 12px;
    text-align: center;
    overflow-wrap: anywhere;
    user-select: all;
  }
</style>
