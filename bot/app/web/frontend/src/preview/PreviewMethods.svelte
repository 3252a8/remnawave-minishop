<script>
  import { CreditCard, Send, WalletCards } from "lucide-svelte";

  export let methods = [];

  const icons = [CreditCard, Send, WalletCards, WalletCards];

  function note(index) {
    if (index === 0) return "Visa, Mastercard";
    if (index === 1) return "Быстро и удобно";
    if (index === 2) return "USDT, BTC, ETH";
    return "ЮMoney, СБП и др.";
  }
</script>

<div class="method-grid">
  {#each methods as method, index}
    <div class:active={index === 1} class="method-card">
      <svelte:component this={icons[index] || WalletCards} size={18} />
      <span>
        <strong>{method.name}</strong>
        <small>{note(index)}</small>
      </span>
    </div>
  {/each}
</div>
