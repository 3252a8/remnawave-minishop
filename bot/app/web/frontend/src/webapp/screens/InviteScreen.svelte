<script>
  import { Copy, Gift, Ticket, TriangleAlert } from "$components/ui/icons.js";
  import { Tooltip } from "$components/ui/primitives.js";

  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import Input from "$components/ui/input.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";

  export let referral = {};
  export let referralBonusDetails = [];
  export let referralOneBonusPerReferee = false;
  export let referralWelcomeBonusDays = 0;
  export let promoBusy = false;
  export let promoCode = "";
  export let promoFieldError = "";
  export let promoIsError = false;
  export let promoStatus = "";

  export let applyPromo = () => {};
  export let clearPromoFieldError = () => {};
  export let copyText = () => {};
  export let t = (key) => key;
</script>

<main class="content with-nav">
  <Card class="bonus-card">
    <div class="bonus-card-head">
      <Gift size={42} />
      <div>
        <strong>{t("wa_referral_bonus_overview_title")}</strong>
        {#if referralOneBonusPerReferee}
          <p>{t("wa_referral_bonus_once_note")}</p>
        {/if}
      </div>
    </div>
    <div>
      <h3 class="card-heading">{t("wa_referral_link_title")}</h3>
      <div class="copy-row referral-copy-row">
        <code>{referral.webapp_link || referral.bot_link || t("wa_link_unavailable")}</code>
        <Button class="referral-copy-button" onclick={() => copyText(referral.webapp_link || referral.bot_link, t("wa_link_copied"))}>
          {t("wa_copy")}
          <Copy size={17} />
        </Button>
      </div>
    </div>
    {#if referralBonusDetails.length || referralWelcomeBonusDays > 0}
      <div class="referral-bonus-list">
        {#if referralWelcomeBonusDays > 0}
          <div class="referral-bonus-row">
            <strong>{t("wa_referral_bonus_registration_title")}</strong>
            <small>{t("wa_referral_bonus_friend_days", { days: referralWelcomeBonusDays })}</small>
          </div>
        {/if}
        {#if referralBonusDetails.length}
          <p class="referral-bonus-intro">{t("wa_referral_bonus_paid_intro")}</p>
        {/if}
        {#each referralBonusDetails as bonus, index (bonus.months || index)}
          <div class="referral-bonus-row">
            <strong>{bonus.title || `${bonus.months || "?"}`}</strong>
            <small>{t("wa_referral_bonus_you_days", { days: Number(bonus.inviter_days || 0) })}</small>
            <small>{t("wa_referral_bonus_friend_days", { days: Number(bonus.friend_days || 0) })}</small>
          </div>
        {/each}
      </div>
    {:else}
      <StatusMessage>{t("wa_referral_bonus_not_configured")}</StatusMessage>
    {/if}
  </Card>
  <Card>
    <h3 class="card-heading card-heading-accent promo-heading">
      <Ticket size={18} />
      <span>{t("wa_activate_promo_title")}</span>
    </h3>
    <div class="copy-row">
      <div class="field-error-wrap">
        <Tooltip.Root open={Boolean(promoFieldError)}>
          <Input
            bind:value={promoCode}
            placeholder="PROMO2026"
            class={promoFieldError ? "input-error" : ""}
            on:input={clearPromoFieldError}
          />
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
      <Button variant="outline" onclick={applyPromo} disabled={promoBusy}>
        {t("wa_activate")}
      </Button>
    </div>
    {#if promoStatus && !(promoIsError && promoFieldError)}
      <StatusMessage error={promoIsError}>{promoStatus}</StatusMessage>
    {/if}
  </Card>
</main>
