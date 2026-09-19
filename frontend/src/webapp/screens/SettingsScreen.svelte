<script lang="ts">
  import {
    ArrowRight,
    FileText,
    Handshake,
    Megaphone,
    Send,
    Server,
    Shield,
    UserRound,
    WalletCards,
  } from "$components/ui/icons.js";

  import Card from "$components/ui/card.svelte";
  import { AttentionDot } from "$components/ui/index.js";
  import { LanguageSelect, ThemeSelect } from "$components/patterns/webapp/index.js";
  import PromoActivationCard from "../PromoActivationCard.svelte";
  import TelegramNotificationsBanner from "../TelegramNotificationsBanner.svelte";
  import MenuButtonIcon from "../MenuButtonIcon.svelte";
  import { formatMoney } from "$lib/webapp/formatters.js";
  import { shouldShowUserBalance } from "$lib/webapp/balanceUiPolicy.js";
  import type { ThemeOption } from "$lib/webapp/themePreference.js";
  import type {
    LanguageOption,
    BalanceView,
    MenuButtonView,
    OpenLinkAction,
    StringAction,
    Translate,
    UserProfile,
    VoidAction,
  } from "$lib/webapp/types.js";

  type Props = {
    currentLang?: string;
    balance?: BalanceView;
    currentLanguageOption?: LanguageOption | null;
    emailAuthEnabled?: boolean;
    notificationPreferencesEnabled?: boolean;
    isAdmin?: boolean;
    languageBusy?: boolean;
    languageClickGuard?: boolean;
    languageClickGuardArmed?: boolean;
    languageMenuOpen?: boolean;
    languageOptions?: LanguageOption[];
    menuButtons?: MenuButtonView[];
    partnerSettingsVisible?: boolean;
    privacyPolicyUrl?: string;
    profileAvatarUrl?: string;
    profileEmail?: string;
    profileTelegramId?: string;
    promoActivationVisible?: boolean;
    promoBusy?: boolean;
    promoCode?: string;
    promoFieldError?: string;
    promoIsError?: boolean;
    promoStatus?: string;
    serverStatusUrl?: string;
    serverStatusInternal?: boolean;
    supportUrl?: string;
    themeOptions?: ThemeOption[];
    themePreference?: string;
    themeSwitcherVisible?: boolean;
    telegramNotificationsNeedPrompt?: boolean;
    telegramNotificationsStartLink?: string;
    telegramNotificationsStatus?: string;
    telegramProfileName?: string;
    user?: UserProfile;
    userAgreementUrl?: string;
    userLanguage?: string;
    showLogout?: boolean;
    hasUnlinkedIdentity?: boolean;
    openTelegramNotificationsBot?: VoidAction;
    logout?: VoidAction;
    openAdminPanel?: VoidAction;
    openBalanceTopup?: VoidAction;
    openPartner?: VoidAction;
    openExternalLink?: OpenLinkAction;
    openMenuButton?: (button: MenuButtonView) => void;
    openNotifications?: VoidAction;
    openSecurity?: VoidAction;
    openServerStatus?: VoidAction;
    applyPromo?: VoidAction;
    clearPromoFieldError?: VoidAction;
    setLanguageMenuOpen?: (open: boolean) => void;
    setPromoCode?: StringAction;
    setThemePreference?: StringAction;
    t?: Translate;
    updateAccountLanguage?: StringAction;
  };

  let {
    currentLang = "ru",
    balance = {} as BalanceView,
    currentLanguageOption = null,
    emailAuthEnabled = true,
    notificationPreferencesEnabled = true,
    isAdmin = false,
    languageBusy = false,
    languageClickGuard = false,
    languageClickGuardArmed = false,
    languageMenuOpen = $bindable(false),
    languageOptions = [],
    menuButtons = [],
    partnerSettingsVisible = false,
    privacyPolicyUrl = "",
    profileAvatarUrl = "",
    profileEmail = "",
    profileTelegramId = "",
    promoActivationVisible = false,
    promoBusy = false,
    promoCode = "",
    promoFieldError = "",
    promoIsError = false,
    promoStatus = "",
    serverStatusUrl = "",
    serverStatusInternal = false,
    supportUrl = "",
    themeOptions = [],
    themePreference = "auto",
    themeSwitcherVisible = false,
    telegramNotificationsNeedPrompt = false,
    telegramNotificationsStartLink = "",
    telegramNotificationsStatus = "unknown",
    telegramProfileName = "",
    user = {},
    userAgreementUrl = "",
    userLanguage = "",
    showLogout = true,
    hasUnlinkedIdentity = false,
    openTelegramNotificationsBot = () => {},
    logout = () => {},
    openAdminPanel = () => {},
    openBalanceTopup = () => {},
    openPartner = () => {},
    openExternalLink = () => {},
    openMenuButton = () => {},
    openNotifications = () => {},
    openSecurity = () => {},
    openServerStatus = () => {},
    applyPromo = () => {},
    clearPromoFieldError = () => {},
    setLanguageMenuOpen = () => {},
    setPromoCode = () => {},
    setThemePreference = () => {},
    t = (key) => key,
    updateAccountLanguage = () => {},
  }: Props = $props();

  const showEmailAccount = $derived(emailAuthEnabled || Boolean(user?.email));
  let themeMenuOpen = $state(false);
</script>

<main class="content with-nav">
  <Card class="settings-profile">
    <div class="settings-avatar">
      {#if profileAvatarUrl}
        <img
          src={profileAvatarUrl}
          alt={t("wa_settings_avatar_alt")}
          loading="lazy"
          referrerpolicy="no-referrer"
        />
      {:else}
        <UserRound size={30} />
      {/if}
    </div>
    <div class="settings-profile-meta">
      <strong>{telegramProfileName}</strong>
      {#if showEmailAccount}
        <small>{profileEmail}</small>
      {/if}
      <small>{profileTelegramId}</small>
    </div>
    {#if shouldShowUserBalance(balance)}
      {#if balance.enabled}
        <button
          class="settings-profile-balance"
          type="button"
          onclick={openBalanceTopup}
          aria-label={t("wa_balance_topup_short", {}, "Top up")}
        >
          <WalletCards size={17} />
          <strong>{formatMoney(balance.amount, balance.currency)}</strong>
        </button>
      {:else}
        <div
          class="settings-profile-balance settings-profile-balance-readonly"
          aria-label={t("wa_balance_title", {}, "Balance")}
        >
          <WalletCards size={17} />
          <strong>{formatMoney(balance.amount, balance.currency)}</strong>
        </div>
      {/if}
    {/if}
  </Card>
  {#if telegramNotificationsNeedPrompt}
    <TelegramNotificationsBanner
      startLink={telegramNotificationsStartLink}
      status={telegramNotificationsStatus}
      onOpenBot={openTelegramNotificationsBot}
      {t}
    />
  {/if}
  {#if isAdmin}
    <div class="settings-admin-block">
      <div class="settings-divider" aria-hidden="true"></div>
      <button
        data-webapp-action="open-admin-panel"
        class="settings-row settings-row-admin"
        type="button"
        onclick={openAdminPanel}
      >
        <Shield size={21} />
        <span>
          <strong>{t("wa_settings_admin_panel", {}, "Admin panel")}</strong>
          <small>{t("wa_settings_admin_panel_hint", {}, "Manage the app")}</small>
        </span>
        <ArrowRight size={17} />
      </button>
    </div>
  {/if}
  <div class="settings-links-block">
    <div class="settings-divider" aria-hidden="true"></div>
    {#if notificationPreferencesEnabled}
      <button
        data-webapp-action="open-notifications"
        class="settings-row settings-row-notifications"
        type="button"
        onclick={openNotifications}
      >
        <Megaphone size={21} />
        <span>
          <strong>{t("wa_notification_preferences_title", {}, "Notifications")}</strong>
          <small
            >{t(
              "wa_notification_preferences_hint",
              {},
              "Choose separately what may be sent to your email and Telegram."
            )}</small
          >
        </span>
        <ArrowRight size={17} />
      </button>
      <div class="settings-divider" aria-hidden="true"></div>
    {/if}
    <button
      data-webapp-action="open-security"
      class="settings-row settings-row-security attention-wrap"
      type="button"
      onclick={openSecurity}
    >
      {#if hasUnlinkedIdentity}<AttentionDot />{/if}
      <Shield size={21} />
      <span>
        <strong>{t("wa_security_title", {}, "Security")}</strong>
        <small>{t("wa_security_hint", {}, "Manage how you sign in and recover access")}</small>
      </span>
      <ArrowRight size={17} />
    </button>
    <div class="settings-divider" aria-hidden="true"></div>
  </div>
  {#if promoActivationVisible}
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
  {/if}
  <div class="settings-list" class:settings-list--language-open={languageMenuOpen}>
    {#if partnerSettingsVisible}
      <button
        data-webapp-action="open-partner-program"
        class="settings-row settings-row-partner"
        type="button"
        onclick={openPartner}
      >
        <Handshake size={21} />
        <span>
          <strong>{t("wa_nav_partner")}</strong>
          <small>{t("wa_partner_program_kicker")}</small>
        </span>
        <ArrowRight size={17} />
      </button>
    {/if}
    <LanguageSelect
      bind:open={languageMenuOpen}
      value={currentLang}
      currentOption={currentLanguageOption}
      {userLanguage}
      options={languageOptions}
      disabled={languageBusy}
      clickGuard={languageClickGuard}
      clickGuardArmed={languageClickGuardArmed}
      closeLabel={t("wa_close")}
      label={t("wa_settings_language")}
      onOpenChange={setLanguageMenuOpen}
      onValueChange={updateAccountLanguage}
    />
    {#if themeSwitcherVisible}
      <ThemeSelect
        bind:open={themeMenuOpen}
        value={themePreference}
        options={themeOptions}
        label={t("wa_settings_theme")}
        onValueChange={setThemePreference}
      />
    {/if}
    {#if userAgreementUrl}
      <button
        class="settings-row settings-row-policy"
        type="button"
        onclick={() => openExternalLink(userAgreementUrl)}
      >
        <FileText size={21} />
        <span><strong>{t("wa_settings_user_agreement")}</strong></span>
        <ArrowRight size={17} />
      </button>
    {/if}
    {#if privacyPolicyUrl}
      <button
        class="settings-row settings-row-policy"
        type="button"
        onclick={() => openExternalLink(privacyPolicyUrl)}
      >
        <Shield size={21} />
        <span><strong>{t("wa_settings_privacy_policy")}</strong></span>
        <ArrowRight size={17} />
      </button>
    {/if}
    {#if serverStatusInternal || serverStatusUrl}
      <button
        class="settings-row settings-row-status"
        type="button"
        onclick={serverStatusInternal ? openServerStatus : () => openExternalLink(serverStatusUrl)}
      >
        <Server size={21} />
        <span><strong>{t("wa_server_status_title", {}, "Server status")}</strong></span>
        <ArrowRight size={17} />
      </button>
    {/if}
    {#if supportUrl}
      <button
        class="settings-row settings-row-support"
        type="button"
        onclick={() => openExternalLink(supportUrl)}
      >
        <Send size={21} />
        <span><strong>{t("menu_support_button")}</strong></span>
        <ArrowRight size={17} />
      </button>
    {/if}
    {#if showLogout}
      <button class="settings-row settings-row-logout" type="button" onclick={logout}>
        <UserRound size={21} />
        <span><strong>{t("wa_logout")}</strong><small>{t("wa_end_session")}</small></span>
        <ArrowRight size={17} />
      </button>
    {/if}
  </div>
  {#if menuButtons.length}
    <div class="settings-list settings-menu-buttons">
      {#each menuButtons as button (button.id)}
        <button
          data-webapp-action={`menu-button-${button.id}`}
          class="settings-row settings-row-menu-button"
          type="button"
          onclick={() => openMenuButton(button)}
        >
          <MenuButtonIcon icon={String(button.icon || "")} />
          <span><strong>{button.label}</strong></span>
          <ArrowRight size={17} />
        </button>
      {/each}
    </div>
  {/if}
</main>

<style>
  .settings-profile-balance {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 8px 10px;
    border: 1px solid var(--border);
    border-radius: var(--radius-inner);
    color: var(--text);
    text-align: right;
    background: var(--panel-2);
    cursor: pointer;
    transition:
      border-color 0.18s ease,
      background 0.18s ease;
  }
  .settings-profile-balance:hover {
    border-color: color-mix(in srgb, var(--text) 22%, var(--border));
    background: color-mix(in srgb, var(--text) 5%, var(--panel-2));
  }
  .settings-profile-balance-readonly {
    cursor: default;
  }
  .settings-profile-balance-readonly:hover {
    border-color: var(--border);
    background: var(--panel-2);
  }
  .settings-profile-balance :global(svg) {
    color: var(--muted);
  }
  .settings-profile-balance strong {
    color: var(--text);
    font-size: 13px;
  }
  @media (max-width: 460px) {
    .settings-profile-balance {
      padding: 7px 8px;
    }
    .settings-profile-balance :global(svg) {
      display: none;
    }
    .settings-profile-meta {
      min-width: 0;
    }
    .settings-profile-meta strong,
    .settings-profile-meta small {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
</style>
