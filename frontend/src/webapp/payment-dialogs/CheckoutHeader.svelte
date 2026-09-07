<script lang="ts">
  let {
    compact,
    showPurchaseDescription,
    title,
    description,
    purchaseDescription,
    inline,
  }: {
    compact: boolean;
    showPurchaseDescription: boolean;
    title: string;
    description: string;
    purchaseDescription: string;
    inline: boolean;
  } = $props();
</script>

{#if !compact || showPurchaseDescription}
  <div
    class="payment-checkout-header"
    class:inline
    class:spacious={!compact && showPurchaseDescription && !description}
  >
    {#if !compact}<h2 id="payment-checkout-title">{title}</h2>
      {#if description}<p>{description}</p>{/if}{/if}
    {#if showPurchaseDescription}<div
        class="subscription-purchase-description subscription-purchase-description-header"
      >
        <p>{purchaseDescription}</p>
      </div>{/if}
  </div>
{/if}

<style>
  .payment-checkout-header {
    display: grid;
    gap: 6px;
    min-width: 0;
  }

  .payment-checkout-header.spacious {
    gap: 12px;
  }

  .payment-checkout-header h2 {
    margin: 0;
    color: var(--text);
    font-size: 19px;
    line-height: 1.18;
  }

  .payment-checkout-header > p {
    margin: 0;
    color: var(--muted);
    font-size: 13px;
    line-height: 1.45;
  }

  .payment-checkout-header.inline {
    text-align: center;
  }

  .payment-checkout-header.inline h2 {
    font-size: clamp(25px, 3vw, 32px);
  }

  .payment-checkout-header.inline > p {
    max-width: 480px;
    margin-inline: auto;
    font-size: 14px;
  }
</style>
