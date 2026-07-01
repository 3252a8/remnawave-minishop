<script>
  import { CircleQuestionMark, Copy, Gift, Ticket, TriangleAlert } from "$components/ui/icons.js";
  import { Tooltip } from "$components/ui/primitives.js";

  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import Input from "$components/ui/input.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";

  let {
    referral = {},
    referralBonusDetails = [],
    referralOneBonusPerReferee = false,
    referralWelcomeBonusDays = 0,
    promoBusy = false,
    promoCode = "",
    promoFieldError = "",
    promoIsError = false,
    promoStatus = "",
    applyPromo = () => {},
    setPromoCode = () => {},
    clearPromoFieldError = () => {},
    copyText = () => {},
    t = (key) => key,
  } = $props();

  const tariffBonusSummaries = $derived(
    referralBonusDetails.filter((bonus) => Array.isArray(bonus.details))
  );
  const periodBonusDetails = $derived(
    referralBonusDetails.filter((bonus) => !Array.isArray(bonus.details))
  );
  const usesTariffBonusSummaries = $derived(tariffBonusSummaries.length > 0);
  const promoEffectStatus = $derived(
    !promoIsError && promoStatus ? String(promoStatus).trim() : ""
  );

  function daysRange(minDays, maxDays) {
    return t("wa_referral_bonus_range_days", {
      min: Number(minDays || 0),
      max: Number(maxDays || 0),
    });
  }
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
        <Button
          class="referral-copy-button"
          onclick={() => copyText(referral.webapp_link || referral.bot_link, t("wa_link_copied"))}
        >
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
        {#if usesTariffBonusSummaries}
          <p class="referral-bonus-intro">{t("wa_referral_bonus_depends_on_tariff")}</p>
        {:else if periodBonusDetails.length}
          <p class="referral-bonus-intro">{t("wa_referral_bonus_paid_intro")}</p>
        {/if}
        {#if usesTariffBonusSummaries}
          {#each tariffBonusSummaries as tariffBonus, index (tariffBonus.id || `tariff:${tariffBonus.tariff_key || index}`)}
            <details class="referral-tariff-dropdown">
              <summary class="referral-tariff-summary">
                <span class="referral-tariff-copy">
                  <strong>{tariffBonus.title || tariffBonus.tariff_name}</strong>
                  <small>
                    {t("wa_referral_bonus_you_range", {
                      range: daysRange(tariffBonus.inviter_min_days, tariffBonus.inviter_max_days),
                    })}
                  </small>
                  <small>
                    {t("wa_referral_bonus_friend_range", {
                      range: daysRange(tariffBonus.friend_min_days, tariffBonus.friend_max_days),
                    })}
                  </small>
                </span>
                <CircleQuestionMark class="premium-server-help-icon" size={16} />
              </summary>
              <div class="referral-tariff-details">
                <div class="referral-tariff-detail-list">
                  {#each tariffBonus.details || [] as bonus, detailIndex (bonus.id || `${tariffBonus.tariff_key || index}:${bonus.months || detailIndex}`)}
                    <div class="referral-bonus-row referral-bonus-row-nested">
                      <strong>{bonus.title || `${bonus.months || "?"}`}</strong>
                      <small
                        >{t("wa_referral_bonus_you_days", {
                          days: Number(bonus.inviter_days || 0),
                        })}</small
                      >
                      <small
                        >{t("wa_referral_bonus_friend_days", {
                          days: Number(bonus.friend_days || 0),
                        })}</small
                      >
                    </div>
                  {/each}
                </div>
              </div>
            </details>
          {/each}
        {:else}
          {#each periodBonusDetails as bonus, index (bonus.id || `${bonus.tariff_key || "legacy"}:${bonus.months || index}`)}
            <div class="referral-bonus-row">
              <strong>{bonus.title || `${bonus.months || "?"}`}</strong>
              <small
                >{t("wa_referral_bonus_you_days", {
                  days: Number(bonus.inviter_days || 0),
                })}</small
              >
              <small
                >{t("wa_referral_bonus_friend_days", {
                  days: Number(bonus.friend_days || 0),
                })}</small
              >
            </div>
          {/each}
        {/if}
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
    <div class="copy-row promo-apply-row">
      <div class="field-error-wrap">
        <Tooltip.Root open={Boolean(promoFieldError)}>
          <Input
            value={promoCode}
            placeholder="PROMO2026"
            class={promoFieldError ? "input-error" : ""}
            oninput={(event) => {
              setPromoCode(event.currentTarget.value);
              clearPromoFieldError();
            }}
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
</main>
