<script lang="ts">
  import { ChevronRight } from "$components/ui/icons.js";

  type DisclosureLevel = "section" | "subsection";

  type Props = {
    anchorKey: string;
    contentId: string;
    countLabel: string;
    dirtyLabel?: string;
    level?: DisclosureLevel;
    logoFallback?: string;
    logoLabel?: string;
    logoUrl?: string;
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
    logoFallback = "",
    logoLabel = "",
    logoUrl = "",
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
  const titleClass = $derived(
    isSubsection ? "admin-settings-subsection-title" : "admin-accordion-title"
  );
  const fallbackText = $derived(logoFallback || title.slice(0, 2).toUpperCase());
  let logoFailed = $state(false);

  $effect(() => {
    logoUrl;
    logoFailed = false;
  });
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
    <span class={titleClass}>
      {#if logoUrl || logoFallback}
        <span class="admin-provider-logo" title={logoLabel || title} aria-hidden="true">
          {#if logoUrl && !logoFailed}
            <img src={logoUrl} alt="" loading="lazy" onerror={() => (logoFailed = true)} />
          {:else}
            <span class="admin-provider-logo-fallback">{fallbackText}</span>
          {/if}
        </span>
      {/if}
      {#if isSubsection}
        <strong class="admin-disclosure-title-text">{title}</strong>
      {:else}
        <span class="admin-disclosure-title-text">{title}</span>
      {/if}
    </span>
    <span class={isSubsection ? "admin-settings-subsection-meta" : "admin-accordion-meta"}>
      {countLabel}{#if overriddenLabel}
        · {overriddenLabel}{/if}{#if dirtyLabel}
        · {dirtyLabel}{/if}
    </span>
    <ChevronRight size={iconSize} class="admin-accordion-chev" />
  </button>
</div>
