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
      class="method-card"
      type="button"
      onclick={() => onSelect(method.id)}
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
