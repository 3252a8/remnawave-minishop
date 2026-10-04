<script lang="ts">
  import { Button, Input } from "$components/ui/index.js";
  import type { RichTextLabels } from "./types.js";

  let {
    value = $bindable(""),
    labels,
    disabled = false,
    onConfirm,
  }: {
    value?: string;
    labels: RichTextLabels;
    disabled?: boolean;
    onConfirm: () => void;
  } = $props();
</script>

<div class="rt-link-row">
  <Input
    controlSize="md"
    class="rt-link-input"
    type="url"
    aria-label={labels.link}
    placeholder={labels.linkPlaceholder}
    bind:value
    {disabled}
    onkeydown={(event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      onConfirm();
    }}
  />
  <Button
    class="rt-tool rt-link-apply"
    variant="outline"
    controlSize="md"
    {disabled}
    onclick={onConfirm}
  >
    {labels.linkApply}
  </Button>
</div>

<style>
  .rt-link-row {
    display: flex;
    min-width: 0;
    gap: 6px;
    align-items: center;
  }
  .rt-link-row :global(.rt-link-input) {
    flex: 1 1 0;
    min-width: 0;
  }
  .rt-link-row :global(.rt-link-apply) {
    flex: 0 0 auto;
  }
</style>
