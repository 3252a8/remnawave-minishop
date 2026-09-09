<script lang="ts">
  import { Gift, ArrowRight } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import { giftState } from "$lib/webapp/gifts.svelte.js";
  import type { Translate } from "$lib/webapp/types.js";
  import GiftCard from "./GiftCard.svelte";
  let { t, full = false }: { t: Translate; full?: boolean } = $props();
  let copied = $state(false);
  async function copy(link: string) {
    try {
      await navigator.clipboard.writeText(link);
      copied = true;
    } catch {
      copied = false;
    }
  }
</script>

{#if giftState.enabled || giftState.gifts.length || giftState.token || giftState.pending}
  <Card class="gift-entry">
    <div class="gift-intro">
      <div class="gift-entry-icon"><Gift size={25} /></div>
      <div>
        <h2>{t(full ? "wa_gift_my_gifts" : "wa_gift_entry_title")}</h2>
        {#if giftState.enabled}<p>{t("wa_gift_entry_description")}</p>{/if}
      </div>
      {#if giftState.enabled}<Button
          variant="secondary"
          onclick={() => {
            giftState.purchaseRequested = true;
          }}><span>{t("wa_gift_buy")}</span><ArrowRight size={16} /></Button
        >{/if}
    </div>
    {#if full}
      <div class="gift-list">
        {#if giftState.loading}<p>{t("wa_loading")}</p>
        {:else if giftState.error}<p role="alert">{t("wa_gift_load_failed")}</p>
          <Button variant="secondary" onclick={() => (giftState.revision += 1)}
            >{t("wa_gift_retry")}</Button
          >
        {:else if !giftState.gifts.length}<p>{t("wa_gift_empty")}</p>
        {:else}{#each giftState.gifts as gift (gift.gift_id)}<GiftCard
              {gift}
              {t}
              oncopy={copy}
            />{/each}{/if}
        {#if copied}<p role="status">{t("wa_link_copied")}</p>{/if}
      </div>
    {:else}
      <button
        class="my-gifts"
        onclick={() => {
          giftState.incoming = false;
          giftState.open = true;
        }}
        >{t("wa_gift_my_gifts")}{#if giftState.gifts.length}
          · {giftState.gifts.length}{/if}</button
      >
    {/if}
    {#if giftState.token}<button
        class="my-gifts"
        onclick={() => {
          giftState.incoming = true;
          giftState.open = true;
        }}>{t("wa_gift_pending_link")}</button
      >{/if}
  </Card>
{/if}

<style>
  :global(.card.gift-entry) {
    min-width: 0;
    background: var(--panel);
  }
  .gift-intro {
    display: flex;
    gap: 14px;
    align-items: center;
  }
  .gift-entry-icon {
    color: var(--accent);
    display: flex;
  }
  .gift-intro > div:nth-child(2) {
    flex: 1;
  }
  h2 {
    margin: 0;
    font-size: 17px;
    font-weight: 650;
  }
  p {
    color: var(--muted);
    font-size: 13px;
    line-height: 1.5;
    margin: 6px 0 0;
  }
  .my-gifts {
    border: 0;
    background: transparent;
    color: var(--accent);
    font-size: 12px;
    margin-top: 12px;
    padding: 0;
    cursor: pointer;
  }
  .gift-list {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
    margin-top: 16px;
  }
  @media (max-width: 520px) {
    .gift-intro {
      flex-wrap: wrap;
    }
    .gift-intro :global(button) {
      width: 100%;
    }
  }
</style>
