<script lang="ts">
  import { ChevronRight } from "$components/ui/icons.js";

  type DisclosureLevel = "section" | "subsection";

  type Props = {
    anchorKey: string;
    contentId: string;
    countLabel: string;
    dirtyLabel?: string;
    level?: DisclosureLevel;
    onToggle: () => void;
    open: boolean;
    overriddenLabel?: string;
    title: string;
  };

  let {
    anchorKey,
    contentId,
    countLabel,
    dirtyLabel = "",
    level = "section",
    onToggle,
    open,
    overriddenLabel = "",
    title,
  }: Props = $props();

  const isSubsection = $derived(level === "subsection");
  const triggerClass = $derived(
    isSubsection ? "admin-settings-subsection-trigger" : "admin-accordion-trigger"
  );
  const iconSize = $derived(isSubsection ? 14 : 16);
</script>

<div class="admin-accordion-header">
  <button
    type="button"
    class={triggerClass}
    data-settings-anchor={anchorKey}
    data-state={open ? "open" : "closed"}
    aria-expanded={open}
    aria-controls={contentId}
    onclick={onToggle}
  >
    {#if isSubsection}
      <strong>{title}</strong>
    {:else}
      <span class="admin-accordion-title">{title}</span>
    {/if}
    <span class={isSubsection ? "admin-settings-subsection-meta" : "admin-accordion-meta"}>
      {countLabel}{#if overriddenLabel}
        · {overriddenLabel}{/if}{#if dirtyLabel}
        · {dirtyLabel}{/if}
    </span>
    <ChevronRight size={iconSize} class="admin-accordion-chev" />
  </button>
</div>
