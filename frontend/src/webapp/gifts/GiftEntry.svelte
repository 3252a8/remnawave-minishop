<script lang="ts">
  import ScreenHeading from "$components/patterns/webapp/ScreenHeading.svelte";
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
    <ScreenHeading
      class="gift-intro"
      stackActions
      level={2}
      title={t(full ? "wa_gift_my_gifts" : "wa_gift_entry_title")}
      subtitle={giftState.enabled ? t("wa_gift_entry_description") : ""}
    >
      {#snippet icon()}<Gift />{/snippet}
      {#snippet actions()}
        {#if giftState.enabled}<Button
            variant="secondary"
            onclick={() => {
              giftState.purchaseRequested = true;
            }}><span>{t("wa_gift_buy")}</span><ArrowRight size={16} /></Button
          >{/if}
      {/snippet}
    </ScreenHeading>
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
          <span class="meta-separator" aria-hidden="true"></span>
          {giftState.gifts.length}{/if}</button
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
</style>
