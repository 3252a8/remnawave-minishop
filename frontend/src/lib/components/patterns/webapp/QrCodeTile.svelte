<script lang="ts">
  /**
   * A QR code drawn dark on a white tile, whatever the theme: many camera apps
   * cannot read light-on-dark codes, and the person scanning may use any of them.
   */
  import QRCode from "qrcode";

  type Props = {
    value?: string;
    alt: string;
  };

  let { value = "", alt }: Props = $props();

  const QR_OPTIONS = {
    errorCorrectionLevel: "M",
    margin: 2,
    width: 640,
    color: { dark: "#000000", light: "#ffffff" },
  } as const;

  let qrDataUrl = $state("");

  $effect(() => {
    const text = value.trim();
    qrDataUrl = "";
    if (!text) return;
    let current = true;
    QRCode.toDataURL(text, QR_OPTIONS)
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

<div class="link-qr-tile">
  {#if qrDataUrl}
    <img src={qrDataUrl} {alt} />
  {:else}
    <span class="link-qr-placeholder" aria-hidden="true"></span>
  {/if}
</div>

<style>
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
</style>
