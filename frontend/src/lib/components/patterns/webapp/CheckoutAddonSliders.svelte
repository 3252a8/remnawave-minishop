<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { ArrowDownUp, Pencil, SatelliteDish, Smartphone, X } from "$components/ui/icons.js";
  import Slider from "$components/ui/slider.svelte";
  import { formatMoney } from "$lib/webapp/formatters.js";
  import {
    checkoutTariffSummary,
    isStarsPaymentMethod,
    type BillingPlan,
  } from "$lib/webapp/tariffs.js";
  import type {
    CheckoutAddonDefinition,
    CheckoutAddonKind,
    CheckoutAddonSelection,
    Translate,
  } from "$lib/webapp/types.js";
  import AnimatedNumber from "./AnimatedNumber.svelte";

  let {
    addons = {},
    selection,
    plan = null,
    tariffTitle = "",
    tariffDescription = "",
    method = "",
    currency = "RUB",
    disabled = false,
    t = (key) => key,
    onChange = () => {},
    onInteractionChange = () => {},
  }: {
    addons?: Partial<Record<CheckoutAddonKind, CheckoutAddonDefinition>>;
    selection: CheckoutAddonSelection;
    plan?: BillingPlan | null;
    tariffTitle?: string;
    tariffDescription?: string;
    method?: string;
    currency?: string;
    disabled?: boolean;
    t?: Translate;
    onChange?: (kind: CheckoutAddonKind, extraUnits: number) => void;
    onInteractionChange?: (active: boolean) => void;
  } = $props();

  const kinds: CheckoutAddonKind[] = ["devices", "traffic", "premium_traffic"];
  const summary = $derived(checkoutTariffSummary(plan));
  const hasAdjustableLimits = $derived(
    kinds.some((kind) => Number(addons[kind]?.options?.length || 0) > 1)
  );
  type CardPhase = "compact" | "opening" | "open" | "closing";
  let phase = $state<CardPhase>("compact");
  let phaseTimer: number | undefined;
  let sliderInteracting = $state(false);
  let titleDescriptionWrapped = $state(false);
  let titleLineElement: HTMLElement | undefined;
  let tariffTitleElement: HTMLElement | undefined;
  let tariffDescriptionLineElement: HTMLElement | undefined;
  let tariffDescriptionElement: HTMLElement | undefined;
  let tariffSeparatorElement: HTMLElement | undefined;
  let titleResizeObserver: ResizeObserver | undefined;
  let titleMeasureFrame: number | undefined;
  const editorExpanded = $derived(phase === "opening" || phase === "open");
  const animating = $derived(phase === "opening" || phase === "closing");

  function definitionFor(kind: CheckoutAddonKind): CheckoutAddonDefinition | undefined {
    const definition = addons[kind];
    return definition && definition.options.length > 1 ? definition : undefined;
  }

  function selectedUnits(kind: CheckoutAddonKind): number {
    if (kind === "devices") return Number(selection.device_count || 0);
    if (kind === "traffic")
      return Number(selection.regular_limit_gb ?? addons[kind]?.base_units ?? 0);
    return Number(selection.premium_limit_gb ?? addons[kind]?.base_units ?? 0);
  }

  function optionFor(kind: CheckoutAddonKind) {
    const definition = definitionFor(kind);
    const selected = selectedUnits(kind);
    return definition?.options?.find(
      (option) =>
        Math.abs(
          Number(kind === "devices" ? option.extra_units || 0 : option.total_units || 0) - selected
        ) < 1e-9
    );
  }

  function totalValue(kind: CheckoutAddonKind): number {
    const definition = definitionFor(kind);
    if (definition) {
      return Number(optionFor(kind)?.total_units ?? definition.base_units ?? 0);
    }
    if (kind === "devices") return summary.devices.units;
    if (kind === "traffic") return summary.traffic.units;
    return summary.premiumTraffic.units;
  }

  function valueSuffix(kind: CheckoutAddonKind): string {
    return kind === "devices" ? "" : " GB";
  }

  function limitKnown(kind: CheckoutAddonKind): boolean {
    if (definitionFor(kind)) return true;
    if (kind === "devices") return summary.devices.known;
    if (kind === "traffic") return summary.traffic.known;
    return summary.premiumTraffic.known;
  }

  function limitUnlimited(kind: CheckoutAddonKind): boolean {
    if (definitionFor(kind)) return false;
    if (kind === "devices") return summary.devices.unlimited;
    if (kind === "traffic") return summary.traffic.unlimited;
    return summary.premiumTraffic.unlimited;
  }

  function trafficStrategy(kind: CheckoutAddonKind): string {
    if (kind === "premium_traffic") {
      return String(
        plan?.premium_traffic_limit_strategy || plan?.traffic_limit_strategy || ""
      ).toUpperCase();
    }
    return String(plan?.traffic_limit_strategy || "").toUpperCase();
  }

  function trafficPeriod(kind: CheckoutAddonKind): string {
    const strategy = trafficStrategy(kind);
    if (strategy.includes("MONTH")) return t("wa_checkout_period_month", {}, "per month");
    if (strategy.includes("WEEK")) return t("wa_checkout_period_week", {}, "per week");
    if (strategy.includes("DAY")) return t("wa_checkout_period_day", {}, "per day");
    if (strategy.includes("NO_RESET")) {
      return t("wa_checkout_period_no_reset", {}, "without reset");
    }
    return "";
  }

  function trafficResetHint(kind: CheckoutAddonKind): string {
    const strategy = trafficStrategy(kind);
    if (strategy.includes("MONTH")) return t("wa_traffic_reset_monthly", {}, "Monthly reset");
    if (strategy.includes("WEEK")) return t("wa_traffic_reset_weekly", {}, "Weekly reset");
    if (strategy.includes("DAY")) return t("wa_traffic_reset_daily", {}, "Daily reset");
    if (strategy.includes("NO_RESET")) return t("wa_traffic_reset_none", {}, "No reset");
    return t("wa_checkout_addon_reset_hint", {}, "Resets with the tariff period");
  }

  function title(kind: CheckoutAddonKind): string {
    if (kind === "devices") return t("wa_checkout_addon_devices", {}, "Devices");
    if (limitUnlimited(kind)) {
      return kind === "traffic"
        ? t("wa_checkout_addon_traffic", {}, "Traffic")
        : t("wa_checkout_addon_premium_traffic", {}, "Premium traffic");
    }
    const period = trafficPeriod(kind);
    if (!period) {
      return kind === "traffic"
        ? t("wa_checkout_tariff_traffic_period", {}, "Traffic per period")
        : t("wa_checkout_tariff_premium_period", {}, "Premium traffic per period");
    }
    return kind === "traffic"
      ? t("wa_checkout_tariff_traffic_with_period", { period }, `Traffic ${period}`)
      : t("wa_checkout_tariff_premium_with_period", { period }, `Premium traffic ${period}`);
  }

  function subtitle(kind: CheckoutAddonKind): string {
    const definition = definitionFor(kind);
    if (!definition) {
      if (!limitKnown(kind)) return t("wa_checkout_tariff_not_specified", {}, "Not specified");
      if (limitUnlimited(kind)) return t("wa_checkout_tariff_unlimited", {}, "Unlimited");
      if (kind === "premium_traffic" && totalValue(kind) <= 0) {
        return t("wa_checkout_tariff_not_included", {}, "Not included");
      }
      return t("wa_checkout_addon_included", {}, "Included in the plan");
    }
    const option = optionFor(kind);
    const extra = Number(option?.extra_units || 0);
    const resetHint = kind === "devices" ? "" : trafficResetHint(kind);
    if (extra <= 0) {
      const included = t("wa_checkout_addon_included", {}, "Included in the plan");
      return resetHint ? `${included} · ${resetHint}` : included;
    }
    const price = isStarsPaymentMethod(method)
      ? `${Number(option?.stars_price || 0)} ⭐`
      : formatMoney(option?.price || 0, currency);
    const surcharge = t("wa_checkout_addon_extra_price", { price }, `Add-on: ${price}`);
    return resetHint ? `${surcharge} · ${resetHint}` : surcharge;
  }

  function activateEditing(): void {
    if (!hasAdjustableLimits || phase !== "compact") return;
    phase = "opening";
    schedulePhase("open", 290);
  }

  function deactivateEditing(): void {
    if (phase !== "open") return;
    phase = "closing";
    schedulePhase("compact", 340);
  }

  function schedulePhase(nextPhase: CardPhase, duration: number): void {
    window.clearTimeout(phaseTimer);
    const delay = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : duration;
    phaseTimer = window.setTimeout(() => {
      phase = nextPhase;
      phaseTimer = undefined;
    }, delay);
  }

  function handleSliderInteraction(active: boolean): void {
    if (sliderInteracting === active) return;
    sliderInteracting = active;
    onInteractionChange(active);
  }

  function measureTitleDescriptionFit(): void {
    titleMeasureFrame = undefined;
    if (
      !titleLineElement ||
      !tariffTitleElement ||
      !tariffDescriptionElement ||
      !tariffSeparatorElement
    ) {
      return;
    }
    const titleGap = Number.parseFloat(
      window.getComputedStyle(titleLineElement).getPropertyValue("--checkout-tariff-title-gap")
    );
    const requiredWidth =
      tariffTitleElement.scrollWidth +
      tariffSeparatorElement.scrollWidth +
      tariffDescriptionElement.scrollWidth +
      (Number.isFinite(titleGap) ? titleGap * 2 : 0);
    titleDescriptionWrapped = requiredWidth > titleLineElement.clientWidth + 0.5;
  }

  function scheduleTitleDescriptionMeasurement(): void {
    if (titleMeasureFrame !== undefined) window.cancelAnimationFrame(titleMeasureFrame);
    titleMeasureFrame = window.requestAnimationFrame(measureTitleDescriptionFit);
  }

  onMount(() => {
    titleResizeObserver = new ResizeObserver(scheduleTitleDescriptionMeasurement);
    if (titleLineElement) titleResizeObserver.observe(titleLineElement);
    if (tariffTitleElement) titleResizeObserver.observe(tariffTitleElement);
    if (tariffDescriptionLineElement) titleResizeObserver.observe(tariffDescriptionLineElement);
    if (tariffDescriptionElement) titleResizeObserver.observe(tariffDescriptionElement);
    scheduleTitleDescriptionMeasurement();
  });

  $effect(() => {
    tariffTitle;
    tariffDescription;
    plan?.tariff_name;
    plan?.title;
    plan?.description;
    if (typeof window !== "undefined") scheduleTitleDescriptionMeasurement();
  });

  onDestroy(() => {
    window.clearTimeout(phaseTimer);
    if (titleMeasureFrame !== undefined) window.cancelAnimationFrame(titleMeasureFrame);
    titleResizeObserver?.disconnect();
    if (sliderInteracting) onInteractionChange(false);
  });
</script>

{#snippet addonValue(kind: CheckoutAddonKind)}
  <span class="checkout-addon-value">
    {#if limitUnlimited(kind)}
      <span class="checkout-addon-unlimited">
        {t("wa_checkout_tariff_unlimited", {}, "Unlimited")}
      </span>
    {:else if limitKnown(kind)}
      <AnimatedNumber
        value={totalValue(kind)}
        suffix={valueSuffix(kind)}
        ariaLabel={`${totalValue(kind)}${valueSuffix(kind)}`}
        format={{ maximumFractionDigits: 2 }}
        replaceAnimations={sliderInteracting}
      />
    {:else}
      <span aria-label={t("wa_checkout_tariff_not_specified", {}, "Not specified")}>—</span>
    {/if}
  </span>
{/snippet}

{#snippet limitIcon(kind: CheckoutAddonKind)}
  <span class="checkout-tariff-limit-icon" aria-hidden="true">
    {#if kind === "devices"}
      <Smartphone size={13} strokeWidth={2} />
    {:else if kind === "traffic"}
      <ArrowDownUp size={13} strokeWidth={2} />
    {:else}
      <SatelliteDish size={13} strokeWidth={2} />
    {/if}
  </span>
{/snippet}

{#snippet summaryFacts()}
  <div class="checkout-tariff-facts">
    {#each kinds as kind}
      {@const definition = definitionFor(kind)}
      {#if kind !== "premium_traffic" || definition || limitKnown(kind)}
        <div class:adjustable={Boolean(definition)} class="checkout-tariff-fact">
          {@render addonValue(kind)}
          <span class="checkout-tariff-fact-label">
            {@render limitIcon(kind)}
            <span class="checkout-addon-label">{title(kind)}</span>
          </span>
        </div>
      {/if}
    {/each}
  </div>
{/snippet}

{#snippet editorControls()}
  <div class="checkout-tariff-editor-facts">
    {#each kinds as kind}
      {@const definition = definitionFor(kind)}
      {#if definition}
        <div class="checkout-tariff-editor-fact">
          <div class="checkout-tariff-editor-copy">
            <span class="checkout-tariff-editor-title">
              {@render limitIcon(kind)}
              <span class="checkout-addon-label">{title(kind)}</span>
            </span>
            <small>{subtitle(kind)}</small>
          </div>
          <Slider
            value={selectedUnits(kind)}
            values={definition.options.map((option) =>
              Number(kind === "devices" ? option.extra_units || 0 : option.total_units || 0)
            )}
            ariaLabel={title(kind)}
            {disabled}
            onValueChange={(value) => !disabled && onChange(kind, value)}
            onInteractionChange={handleSliderInteraction}
          />
        </div>
      {/if}
    {/each}
  </div>

  {#if disabled}
    <small class="checkout-addon-unavailable">
      {t(
        "wa_checkout_addons_method_unavailable",
        {},
        "Choose another payment method to add extras"
      )}
    </small>
  {/if}
{/snippet}

<section
  class:has-adjustable-limits={hasAdjustableLimits}
  class:is-editing={editorExpanded}
  class:is-opening={phase === "opening"}
  class:is-closing={phase === "closing"}
  class:is-animating={animating}
  class="checkout-tariff-card"
>
  {#if hasAdjustableLimits && phase === "compact"}
    <button
      class="checkout-tariff-summary-button"
      type="button"
      aria-label={`${t("wa_checkout_tariff_edit", {}, "Change tariff limits")}: ${tariffTitle || plan?.tariff_name || plan?.title || ""}`}
      title={t("wa_checkout_tariff_edit", {}, "Change tariff limits")}
      onclick={activateEditing}
    ></button>
  {/if}

  <header class="checkout-tariff-card-head">
    <span
      class:is-wrapped={titleDescriptionWrapped}
      class="checkout-tariff-title-line"
      bind:this={titleLineElement}
    >
      <strong bind:this={tariffTitleElement}>
        {tariffTitle || plan?.tariff_name || plan?.title || ""}
      </strong>
      <span class="checkout-tariff-description-line" bind:this={tariffDescriptionLineElement}>
        <span
          class="checkout-tariff-title-separator"
          aria-hidden="true"
          bind:this={tariffSeparatorElement}
        >
          —
        </span>
        <small bind:this={tariffDescriptionElement}>
          {tariffDescription ||
            plan?.description ||
            t("wa_tariff_no_description", {}, "Tariff description is not configured")}
        </small>
      </span>
    </span>
    {#if hasAdjustableLimits}
      <button
        class:checkout-tariff-close={phase !== "compact"}
        class="checkout-tariff-edit checkout-tariff-toggle"
        type="button"
        aria-label={phase !== "compact"
          ? t("wa_close", {}, "Close")
          : t("wa_checkout_tariff_edit", {}, "Change tariff limits")}
        title={phase !== "compact"
          ? t("wa_close", {}, "Close")
          : t("wa_checkout_tariff_edit", {}, "Change tariff limits")}
        aria-disabled={animating}
        onclick={phase === "compact" ? activateEditing : deactivateEditing}
      >
        {#if phase !== "compact"}
          <X size={14} />
        {:else}
          <Pencil size={14} />
        {/if}
      </button>
    {/if}
  </header>

  <div class="checkout-tariff-summary-static">
    {@render summaryFacts()}
  </div>

  {#if hasAdjustableLimits}
    <div class="checkout-tariff-editor-mode" aria-hidden={!editorExpanded} inert={!editorExpanded}>
      <div class="checkout-tariff-editor-clip">
        <div class="checkout-tariff-editor-inner">
          {@render editorControls()}
        </div>
      </div>
    </div>
  {/if}
</section>
