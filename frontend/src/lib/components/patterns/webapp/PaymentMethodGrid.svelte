<script lang="ts">
  import type { Component } from "svelte";
  import * as Icons from "$components/ui/icons.js";
  import type { PaymentMethod, StringAction, Translate } from "$lib/webapp/types.js";

  type IconComponent = Component<{ size?: number | string }>;
  const iconRegistry: Record<string, unknown> = Icons;

  let {
    methods = [],
    selectedMethod = "",
    t = (key) => key,
    onSelect = () => {},
  }: {
    methods?: PaymentMethod[];
    selectedMethod?: string;
    t?: Translate;
    onSelect?: StringAction;
  } = $props();

  function methodId(method: PaymentMethod): string {
    return String(method?.id || "");
  }

  function methodTitle(method: PaymentMethod) {
    return typeof method?.name === "string" && method.name ? method.name : t("wa_method_other_title");
  }

  function methodIcon(method: PaymentMethod): IconComponent | null {
    const iconName = String(method?.icon || "").trim();
    const icon = iconName ? iconRegistry[iconName] : null;
    return typeof icon === "function" ? (icon as IconComponent) : null;
  }

  function disabledTitle(method: PaymentMethod) {
    if (!method?.disabled || !method?.min_amount || !method?.min_currency) return "";
    return `Minimum ${method.min_amount} ${method.min_currency}`;
  }
</script>

<div
  class:method-grid-single={methods.length === 1}
  class:method-grid-many={methods.length > 2}
  class="method-grid"
>
  {#each methods as method}
    {@const Icon = methodIcon(method)}
    {@const id = methodId(method)}
    <button
      class:active={selectedMethod === id}
      class:disabled={method.disabled}
      class="method-card"
      disabled={method.disabled}
      title={disabledTitle(method)}
      type="button"
      onclick={() => !method.disabled && onSelect(id)}
    >
      <span class="method-card-main">
        {#if Icon}
          <Icon size={19} />
        {/if}
        <strong>{methodTitle(method)}</strong>
      </span>
    </button>
  {/each}
</div>
