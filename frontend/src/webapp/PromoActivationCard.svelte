<script lang="ts">
  import { Ticket, TriangleAlert, X } from "$components/ui/icons.js";
  import { Tooltip } from "$components/ui/primitives.js";

  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import Input from "$components/ui/input.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";
  import type { StringAction, Translate, VoidAction } from "$lib/webapp/types.js";

  type Props = {
    applyPromo?: VoidAction;
    clearPromoFieldError?: VoidAction;
    promoBusy?: boolean;
    promoCode?: string;
    promoFieldError?: string;
    promoIsError?: boolean;
    promoStatus?: string;
    setPromoCode?: StringAction;
    t?: Translate;
  };

  let {
    promoBusy = false,
    promoCode = "",
    promoFieldError = "",
    promoIsError = false,
    promoStatus = "",
    applyPromo = () => {},
    setPromoCode = () => {},
    clearPromoFieldError = () => {},
    t = (key) => key,
  }: Props = $props();

  const promoCodeText = $derived(String(promoCode || ""));
  const hasPromoCode = $derived(Boolean(promoCodeText.trim()));
  const promoEffectStatus = $derived(
    !promoIsError && hasPromoCode && promoStatus ? String(promoStatus).trim() : ""
  );

  function clearPromoCode(): void {
    setPromoCode("");
    clearPromoFieldError();
  }
</script>

<Card>
  <h3 class="card-heading card-heading-accent promo-heading">
    <Ticket size={18} />
    <span>{t("wa_activate_promo_title")}</span>
  </h3>
  <div class="copy-row promo-apply-row">
    <div
      class="field-error-wrap promo-code-input-wrap"
      class:promo-input-has-clear={hasPromoCode}
      class:promo-input-has-error={Boolean(promoFieldError)}
    >
      <Tooltip.Root open={Boolean(promoFieldError)}>
        <Input
          value={promoCode}
          maxlength={100}
          placeholder="PROMO2026"
          readonly={Boolean(promoEffectStatus)}
          class={[
            "promo-code-input",
            promoFieldError ? "input-error" : "",
            promoEffectStatus ? "is-applied" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          oninput={(event) => {
            setPromoCode(event.currentTarget.value);
            clearPromoFieldError();
          }}
        />
        {#if hasPromoCode}
          <button
            class="checkout-promo-clear promo-code-clear"
            type="button"
            onclick={clearPromoCode}
            aria-label={t("wa_remove")}
          >
            <X size={14} />
          </button>
        {/if}
        {#if promoFieldError}
          <Tooltip.Trigger class="field-error-trigger" aria-label={promoFieldError}>
            <span class="field-error-icon" aria-hidden="true"><TriangleAlert size={18} /></span>
          </Tooltip.Trigger>
        {/if}
        {#if promoFieldError}
          <Tooltip.Portal>
            <Tooltip.Content class="field-error-tooltip">{promoFieldError}</Tooltip.Content>
          </Tooltip.Portal>
        {/if}
      </Tooltip.Root>
    </div>
    {#if promoEffectStatus}
      <span class="checkout-promo-discount-marker promo-status-chip" title={promoEffectStatus}>
        {promoEffectStatus}
      </span>
    {:else}
      <Button variant="outline" onclick={applyPromo} disabled={promoBusy}>
        {t("wa_activate")}
      </Button>
    {/if}
  </div>
  {#if promoStatus && (promoIsError ? !promoFieldError : !promoEffectStatus)}
    <StatusMessage error={promoIsError}>{promoStatus}</StatusMessage>
  {/if}
</Card>
