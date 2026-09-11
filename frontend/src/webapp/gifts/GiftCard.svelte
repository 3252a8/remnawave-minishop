<script lang="ts">
  import { CheckCircle2, Gift } from "$components/ui/icons.js";
  import CopyLinkField from "$components/patterns/CopyLinkField.svelte";
  import type { GiftView } from "$lib/webapp/gifts.svelte.js";
  import type { Translate } from "$lib/webapp/types.js";
  let {
    gift,
    t,
    oncopy = () => {},
  }: { gift: GiftView; t: Translate; oncopy?: (link: string) => void } = $props();
</script>

<article class="gift-card">
  <div class="gift-card-heading">
    <div class="gift-icon"><Gift size={24} /></div>
    <div>
      <strong>{gift.tariff_title || t("wa_subscription_title")}</strong>
      <p>{t("wa_gift_days", { days: gift.duration_days })}</p>
    </div>
    <span class:activated={gift.status === "activated"} class="gift-status"
      >{#if gift.status === "activated"}<CheckCircle2 size={13} />{/if}{t(
        `wa_gift_status_${gift.status}`
      )}</span
    >
  </div>
  <div class="gift-details">
    {#if gift.bonus_days}<span>{t("wa_gift_bonus_days", { days: gift.bonus_days })}</span>{/if}
    {#if gift.regular_bonus_gb}<span
        >{t("wa_gift_bonus_traffic", { gb: gift.regular_bonus_gb })}</span
      >{/if}
    {#if gift.premium_bonus_gb}<span
        >{t("wa_gift_bonus_premium_traffic", { gb: gift.premium_bonus_gb })}</span
      >{/if}
    {#if gift.devices != null}<span
        >{gift.devices > 0
          ? t("wa_gift_devices", { count: gift.devices })
          : t("wa_gift_devices_unlimited")}</span
      >{/if}
    {#if gift.regular_limit_gb != null}<span
        >{gift.regular_limit_gb === 0
          ? t("wa_gift_traffic_unlimited")
          : t("wa_gift_traffic", { gb: gift.regular_limit_gb })}</span
      >{/if}
    {#if gift.premium_unlimited}<span>{t("wa_gift_premium_unlimited")}</span
      >{:else if gift.premium_limit_gb != null}<span
        >{t("wa_gift_premium", { gb: gift.premium_limit_gb })}</span
      >{/if}
  </div>
  {#if gift.link}
    <CopyLinkField
      class="gift-copy"
      value={gift.link}
      inputLabel={t("wa_copy_link_label")}
      copyLabel={t("wa_copy")}
      {oncopy}
    />
    <p class="gift-hint">{t("wa_gift_link_private")}</p>
  {/if}
  {#if gift.activated_at}<p class="gift-hint">
      {t("wa_gift_activated_on", { date: new Date(gift.activated_at).toLocaleDateString() })}
    </p>{/if}
  {#if gift.recipient_email}<p class="gift-hint">
      {gift.recipient_email} · {t(`wa_gift_delivery_${gift.delivery_status || "pending"}`)}
    </p>{/if}
</article>

<style>
  .gift-card {
    min-width: 0;
    overflow-wrap: anywhere;
    border: 1px solid var(--border);
    border-radius: var(--radius-card);
    padding: 16px;
    background: var(--panel);
  }
  .gift-card-heading {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .gift-card-heading > div:nth-child(2) {
    min-width: 0;
  }
  .gift-icon {
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    border-radius: var(--radius-inner);
    padding: 12px;
    display: flex;
  }
  strong {
    font-size: 16px;
  }
  p {
    margin: 5px 0 0;
    color: var(--muted);
    font-size: 13px;
  }
  .gift-status {
    margin-left: auto;
    display: flex;
    gap: 5px;
    align-items: center;
    font-size: 11px;
    font-weight: 600;
    border-radius: var(--radius-card);
    padding: 6px 9px;
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    color: var(--accent);
    white-space: nowrap;
  }
  .gift-status.activated {
    color: var(--success, #22c55e);
    background: color-mix(in srgb, var(--success, #22c55e) 10%, transparent);
  }
  .gift-details {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 16px;
    font-size: 12px;
    color: var(--muted);
  }
  .gift-details span {
    background: var(--surface-muted);
    padding: 6px 10px;
    border-radius: var(--radius-inner);
  }
  .gift-card :global(.gift-copy) {
    min-width: 0;
    margin-top: 12px;
  }
  .gift-hint {
    font-size: 12px;
    line-height: 1.5;
    margin-top: 12px;
  }
  @media (max-width: 480px) {
    .gift-card {
      padding: 16px;
    }
    .gift-card-heading {
      flex-wrap: wrap;
    }
    .gift-status {
      margin-left: 0;
    }
  }
</style>
