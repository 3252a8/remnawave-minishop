<script lang="ts">
  import * as Icons from "$components/ui/icons.js";

  type AnyRecord = Record<string, any>;
  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    methods = [],
    selectedMethod = "",
    t = (key) => key,
    onSelect = () => {},
  }: {
    methods?: AnyRecord[];
    selectedMethod?: string;
    t?: Translate;
    onSelect?: (id: string) => void;
  } = $props();

  function methodTitle(method: AnyRecord) {
    return method?.name || t("wa_method_other_title");
  }

  function methodIcon(method: AnyRecord) {
    const iconName = String(method?.icon || "").trim();
    return iconName ? (Icons as AnyRecord)[iconName] || null : null;
  }

  function disabledTitle(method: AnyRecord) {
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
    <button
      class:active={selectedMethod === method.id}
      class:disabled={method.disabled}
      class="method-card"
      disabled={method.disabled}
      title={disabledTitle(method)}
      type="button"
      onclick={() => !method.disabled && onSelect(method.id)}
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
