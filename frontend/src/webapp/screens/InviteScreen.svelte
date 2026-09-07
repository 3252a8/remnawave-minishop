<script lang="ts">
  import GiftEntry from "../gifts/GiftEntry.svelte";
  import { CircleQuestionMark, Gift } from "$components/ui/icons.js";

  import CopyLinkField from "$components/patterns/CopyLinkField.svelte";
  import Card from "$components/ui/card.svelte";
  import { StatusMessage } from "$components/patterns/webapp/index.js";
  import { visibleReferralLinks } from "$lib/webapp/referralLinks.js";
  import PromoActivationCard from "../PromoActivationCard.svelte";
  import type {
    CopyTextAction,
    ReferralBonusDetail,
    ReferralState,
    StringAction,
    Translate,
    VoidAction,
  } from "$lib/webapp/types.js";

  type Props = {
    applyPromo?: VoidAction;
    clearPromoFieldError?: VoidAction;
    copyText?: CopyTextAction;
    promoBusy?: boolean;
    promoCode?: string;
    promoFieldError?: string;
    promoIsError?: boolean;
    promoStatus?: string;
    referral?: ReferralState;
    referralProgramEnabled?: boolean;
    referralBonusDetails?: ReferralBonusDetail[];
    referralOneBonusPerReferee?: boolean;
    referralWelcomeBonusDays?: number;
    setPromoCode?: StringAction;
    t?: Translate;
  };

  let {
    referral = {},
    referralProgramEnabled = true,
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
    copyText = async () => {},
    t = (key) => key,
  }: Props = $props();

  const tariffBonusSummaries = $derived(
    referralBonusDetails.filter((bonus) => Array.isArray(bonus.details))
  );
  const periodBonusDetails = $derived(
    referralBonusDetails.filter((bonus) => !Array.isArray(bonus.details))
  );
  const usesTariffBonusSummaries = $derived(tariffBonusSummaries.length > 0);
  const referralLinks = $derived(visibleReferralLinks(referral));

  function daysRange(minDays: unknown, maxDays: unknown): string {
    return t("wa_referral_bonus_range_days", {
      min: Number(minDays || 0),
      max: Number(maxDays || 0),
    });
  }
</script>

<main class="content with-nav">
  <GiftEntry {t} full />
  <PromoActivationCard
    {promoCode}
    {promoFieldError}
    {promoBusy}
    {promoIsError}
    {promoStatus}
    {applyPromo}
    {setPromoCode}
    {clearPromoFieldError}
    {t}
  />
  {#if referralProgramEnabled}<section class="referral-program-shell">
      <div class="referral-program-content">
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
            {#if referralLinks.length}
              <div class="referral-link-list">
                {#each referralLinks as link (link.id)}
                  <div class="referral-link-item">
                    <small class="referral-link-label">{t(link.labelKey)}</small>
                    <CopyLinkField
                      value={link.url}
                      inputLabel={t(link.labelKey)}
                      copyLabel={t("wa_copy")}
                      oncopy={(value) => copyText(value, t("wa_link_copied"))}
                    />
                  </div>
                {/each}
              </div>
            {:else}
              <CopyLinkField
                inputLabel={t("wa_copy_link_label")}
                copyLabel={t("wa_copy")}
                unavailableLabel={t("wa_link_unavailable")}
              />
            {/if}
          </div>
          {#if referralBonusDetails.length || referralWelcomeBonusDays > 0}
            <div class="referral-bonus-list">
              {#if referralWelcomeBonusDays > 0}
                <div class="referral-bonus-row">
                  <strong>{t("wa_referral_bonus_registration_title")}</strong>
                  <small
                    >{t("wa_referral_bonus_friend_days", {
                      days: referralWelcomeBonusDays,
                    })}</small
                  >
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
                            range: daysRange(
                              tariffBonus.inviter_min_days,
                              tariffBonus.inviter_max_days
                            ),
                          })}
                        </small>
                        <small>
                          {t("wa_referral_bonus_friend_range", {
                            range: daysRange(
                              tariffBonus.friend_min_days,
                              tariffBonus.friend_max_days
                            ),
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
      </div>
    </section>{/if}
</main>
