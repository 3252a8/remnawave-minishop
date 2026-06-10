<script>
  import * as Icons from "$components/ui/icons.js";

  export let methods = [];
  export let selectedMethod = "";
  export let t = (key) => key;
  export let onSelect = () => {};

  function methodTitle(method) {
    return method?.name || t("wa_method_other_title");
  }

  function methodIcon(method) {
    const iconName = String(method?.icon || "").trim();
    return iconName ? Icons[iconName] || null : null;
  }

  function disabledTitle(method) {
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
    {@const icon = methodIcon(method)}
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
        {#if icon}
          <svelte:component this={icon} size={19} />
        {/if}
        <strong>{methodTitle(method)}</strong>
      </span>
    </button>
  {/each}
</div>
