<script>
  import { Bitcoin, CreditCard } from "$components/ui/icons.js";

  export let methods = [];
  export let selectedMethod = "";
  export let t = (key) => key;
  export let onSelect = () => {};

  function methodMeta(method) {
    const id = String(method?.id || "").toLowerCase();
    if (id.includes("platega_sbp")) return { title: t("wa_method_platega_sbp_card"), icon: CreditCard };
    if (id.includes("platega_crypto")) return { title: t("wa_method_platega_crypto"), icon: Bitcoin };
    if (id.includes("yookassa") || id.includes("card")) return { title: t("pay_with_yookassa_button"), icon: null };
    if (id.includes("severpay")) return { title: t("pay_with_severpay_button"), icon: null };
    if (id.includes("freekassa")) return { title: t("pay_with_sbp_button"), icon: null };
    if (id.includes("cryptopay") || id.includes("crypto")) return { title: t("pay_with_cryptopay_button"), icon: null };
    if (id.includes("stars")) return { title: t("pay_with_stars_button"), icon: null };
    if (id.includes("sbp")) return { title: t("pay_with_sbp_button"), icon: null };
    return { title: t("wa_method_other_title"), icon: null };
  }
</script>

<div class="method-grid">
  {#each methods as method}
    {@const meta = methodMeta(method)}
    <button
      class:active={selectedMethod === method.id}
      class="method-card"
      type="button"
      onclick={() => onSelect(method.id)}
    >
      <span class="method-card-main">
        {#if meta.icon}
          <svelte:component this={meta.icon} size={19} />
        {/if}
        <strong>{meta.title}</strong>
      </span>
    </button>
  {/each}
</div>
