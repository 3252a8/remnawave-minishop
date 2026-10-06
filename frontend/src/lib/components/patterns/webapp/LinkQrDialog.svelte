<script lang="ts">
  /**
   * Shows a link as a QR code for someone else's phone camera to open.
   *
   * The code is always dark on a white tile, whatever the theme: many camera
   * apps cannot read light-on-dark codes, and the person scanning may use any
   * of them.
   */
  import QrCodeTile from "./QrCodeTile.svelte";
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
</script>

<Dialog {open} {title} {description} {closeLabel} {onclose} class="link-qr-dialog">
  <div class="link-qr">
    <QrCodeTile value={open ? link : ""} {alt} />
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
