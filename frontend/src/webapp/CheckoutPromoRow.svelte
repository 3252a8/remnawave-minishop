<script lang="ts">
  import { X } from "$components/ui/icons.js";

  import Button from "$components/ui/button.svelte";
  import Input from "$components/ui/input.svelte";

  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type VoidAction = () => void;

  const noop: VoidAction = () => {};
  const defaultTranslate: Translate = (key) => key;

  let {
    appliedCode = "",
    inputId = "",
    inputName = "",
    isError = false,
    onApply = noop,
    onClear = noop,
    status = "",
    t = defaultTranslate,
    value = $bindable(""),
  }: {
    appliedCode?: string;
    inputId?: string;
    inputName?: string;
    isError?: boolean;
    onApply?: VoidAction;
    onClear?: VoidAction;
    status?: string;
    t?: Translate;
    value?: string;
  } = $props();

  const hasAppliedCode = $derived(Boolean(appliedCode));
  const statusText = $derived(String(status || "").trim());
  const markerText = $derived(statusText || t("wa_promo_applied", {}, "Applied"));
</script>

<div
  class="checkout-promo-row"
  class:is-applied={hasAppliedCode}
  class:is-error={Boolean(isError && statusText)}
  title={statusText}
>
  <div class="checkout-promo-input-wrap">
    <Input
      id={inputId}
      name={inputName}
      class="checkout-promo-input"
      bind:value
      readonly={hasAppliedCode}
      aria-invalid={Boolean(isError && statusText)}
      placeholder={t("wa_promo_enter")}
    />
    {#if hasAppliedCode}
      <button
        class="checkout-promo-clear"
        type="button"
        onclick={onClear}
        aria-label={t("wa_remove")}
      >
        <X size={14} />
      </button>
    {/if}
  </div>
  <div class="checkout-promo-action">
    {#if hasAppliedCode}
      <span class="checkout-promo-discount-marker">{markerText}</span>
    {:else}
      <Button variant="secondary" onclick={onApply} disabled={!value.trim()}>
        {t("wa_apply")}
      </Button>
    {/if}
  </div>
</div>
