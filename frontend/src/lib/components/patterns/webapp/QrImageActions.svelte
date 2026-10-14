<script lang="ts">
  import type { Snippet } from "svelte";
  import Button from "$components/ui/button.svelte";
  import { Check, Copy, Download } from "$components/ui/icons.js";
  import { copyQrImage, createQrImage, downloadQrImage } from "$lib/webapp/qrImage.js";
  import type { Translate } from "$lib/webapp/types.js";

  let {
    value,
    t,
    filename = "qr-code.png",
    layout = "buttons",
    preview,
  }: {
    value: string;
    t: Translate;
    filename?: string;
    layout?: "buttons" | "icon-column";
    preview?: Snippet;
  } = $props();
  let image = $state("");
  let busy = $state(false);
  let copied = $state(false);
  let status = $state("");
  let generation = 0;
  $effect(() => {
    const currentValue = value;
    generation += 1;
    let active = true;
    image = "";
    busy = false;
    copied = false;
    status = "";
    void createQrImage(currentValue)
      .then((result) => {
        if (active) image = result;
      })
      .catch(() => {
        if (active) status = t("wa_qr_image_failed");
      });
    return () => {
      active = false;
    };
  });

  async function copyImage() {
    if (!image || busy) return;
    const currentGeneration = generation;
    busy = true;
    copied = false;
    status = "";
    try {
      await copyQrImage(image);
      if (generation === currentGeneration) {
        copied = true;
        status = t("wa_qr_image_copied");
      }
    } catch {
      if (generation === currentGeneration) status = t("wa_qr_copy_unavailable");
    } finally {
      if (generation === currentGeneration) busy = false;
    }
  }
  async function downloadImage() {
    if (!image || busy) return;
    const currentGeneration = generation;
    busy = true;
    status = "";
    try {
      await downloadQrImage(image, filename);
    } catch (error) {
      if (
        generation === currentGeneration &&
        !(error instanceof Error && error.name === "AbortError")
      )
        status = t("wa_qr_download_failed");
    } finally {
      if (generation === currentGeneration) busy = false;
    }
  }
</script>

<div class="qr-image-actions" class:is-icon-column={layout === "icon-column"}>
  {#if preview}<div class="qr-image-preview">{@render preview()}</div>{/if}
  <div class="qr-image-buttons">
    <Button
      variant="secondary"
      size={layout === "icon-column" ? "icon-sm" : "default"}
      aria-label={t("wa_qr_copy_image")}
      title={t("wa_qr_copy_image")}
      disabled={!image || busy}
      onclick={copyImage}
    >
      {#if copied}<Check size={16} />{:else}<Copy size={16} />{/if}
      {#if layout === "buttons"}{t("wa_qr_copy_image")}{/if}
    </Button>
    <Button
      variant="secondary"
      size={layout === "icon-column" ? "icon-sm" : "default"}
      aria-label={t("wa_qr_download_png")}
      title={t("wa_qr_download_png")}
      disabled={!image || busy}
      onclick={downloadImage}
    >
      <Download size={16} />{#if layout === "buttons"}{t("wa_qr_download_png")}{/if}
    </Button>
  </div>
  {#if status}<p role="status">{status}</p>{/if}
</div>

<style>
  .qr-image-actions {
    display: grid;
    gap: 8px;
    width: 100%;
    min-width: 0;
  }
  .qr-image-buttons {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 8px;
  }
  .is-icon-column {
    width: auto;
    max-width: 100%;
    grid-template-columns: minmax(0, 204px) 36px;
    align-items: start;
  }
  .is-icon-column .qr-image-buttons {
    flex-direction: column;
    align-items: stretch;
    flex-wrap: nowrap;
  }
  .is-icon-column .qr-image-buttons :global(button) {
    width: 36px;
    height: 36px;
    min-height: 36px;
    padding: 0;
  }
  .qr-image-preview {
    min-width: 0;
  }
  .is-icon-column p {
    grid-column: 1 / -1;
  }
  p {
    color: var(--muted);
    font-size: 12px;
    line-height: 1.5;
    margin: 0;
    text-align: center;
    overflow-wrap: anywhere;
  }
</style>
