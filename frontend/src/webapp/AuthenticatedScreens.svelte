<script lang="ts">
  import type { LanguageOption } from "../lib/webapp/languageView.js";
  import type { DevicesStore } from "../lib/webapp/stores/devicesStore.js";
  import type { SupportStore } from "../lib/webapp/stores/supportStore.js";

  import WebAppShell from "./WebAppShell.svelte";
  import DevicesScreen from "./screens/DevicesScreen.svelte";
  import HomeScreen from "./screens/HomeScreen.svelte";
  import InstallGuideScreen from "./screens/InstallGuideScreen.svelte";
  import InviteScreen from "./screens/InviteScreen.svelte";
  import SettingsScreen from "./screens/SettingsScreen.svelte";
  import SupportScreen from "./screens/SupportScreen.svelte";
  import SupportTicketScreen from "./screens/SupportTicketScreen.svelte";
  import TrialActivationScreen from "./screens/TrialActivationScreen.svelte";
  import type { TrialActivationResult } from "$lib/webapp/types.js";

  type AnyRecord = Record<string, any>;
  type Action = (...args: any[]) => any;
  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  type Props = {
    accountStore: AnyRecord;
    activateTrial: Action;
    activeTab?: string;
    appSettings?: AnyRecord;
    applyPromo: Action;
    autoRenewBusy?: boolean;
    brand?: AnyRecord;
    brandTitle?: string;
    canChangeTariff?: boolean;
    clearPromoFieldError: Action;
    copyText: Action;
    currentLang?: string;
    currentLanguageOption?: LanguageOption | null;
    currentTariffName?: string;
    devicesBusy?: boolean;
    devicesData?: AnyRecord | null;
    devicesEnabled?: boolean;
    devicesErrorCode?: string;
    devicesIsError?: boolean;
    devicesLoaded?: boolean;
    devicesStatus?: string;
    devicesStore: DevicesStore;
    emailAuthEnabled?: boolean;
    emailLinkStatus?: string;
    goDevices: Action;
    goHome: Action;
    goInvite: Action;
    goSettings: Action;
    goSupport: Action;
    hasActiveTariffSubscription?: boolean;
    hasMultipleTariffs?: boolean;
    hasUnlinkedIdentity?: boolean;
    isAdmin?: boolean;
    languageBusy?: boolean;
    languageClickGuard?: boolean;
    languageClickGuardArmed?: boolean;
    languageMenuOpen?: boolean;
    languageOptions?: LanguageOption[];
    linkEmailBusy?: boolean;
    linkTelegramAccount: Action;
    linkTelegramAndActivateTrial: Action;
    linkTelegramAndClaimReferralWelcome: Action;
    linkTelegramBusy?: boolean;
    loadDevices: Action;
    openAdminPanel: Action;
    openAppLink: Action;
    openConnectLink: Action;
    openDeviceTopupModal: Action;
    openExternalLink: Action;
    openInstallOrConnect: Action;
    openLinkEmailDialog: Action;
    openPaymentModal: Action;
    openPremiumTopupModal: Action;
    openRegularTopupModal: Action;
    openSetPasswordDialog: Action;
    openTariffChangeModal: Action;
    openTelegramNotificationsBot: Action;
    openTrialInstallOrConnect: Action;
    premiumTrafficTopupBarClickable?: boolean;
    premiumTrafficTopupUnlocked?: boolean;
    primaryPayActionLabel: () => string;
    privacyPolicyUrl?: string;
    profileAvatarUrl?: string;
    profileEmail?: string;
    profileTelegramId?: string;
    promoBusy?: boolean;
    promoCode?: string;
    promoFieldError?: string;
    promoIsError?: boolean;
    promoStatus?: string;
    referral?: AnyRecord;
    referralBonusDetails?: AnyRecord[];
    referralOneBonusPerReferee?: boolean;
    referralWelcomeBonusDays?: number;
    regularTrafficTopupBarClickable?: boolean;
    regularTrafficTopupUnlocked?: boolean;
    screen?: string;
    serverStatusUrl?: string;
    setLanguageMenuOpen: (open: boolean) => void;
    setPromoCode: (value: string) => void;
    subscription?: AnyRecord;
    supportEnabled?: boolean;
    supportStore: SupportStore;
    supportUnreadCount?: number;
    supportUnreadLoaded?: boolean;
    supportUnreadLoading?: boolean;
    supportUrl?: string;
    t: Translate;
    telegramMiniAppContext?: boolean;
    telegramNotificationsNeedPrompt?: boolean;
    telegramNotificationsStartLink?: string;
    telegramNotificationsStatus?: string;
    telegramPlatform?: string;
    telegramProfileName?: string;
    termUnitLabel: Action;
    toggleAutoRenew: Action;
    trafficMode?: boolean;
    trialActivationError?: string;
    trialActivationResult?: TrialActivationResult | null;
    trialBusy?: boolean;
    user?: AnyRecord;
    userAgreementUrl?: string;
    userLanguage?: string;
  };

  let {
    accountStore,
    activateTrial,
    activeTab = "home",
    appSettings = {},
    applyPromo,
    autoRenewBusy = false,
    brand = {},
    brandTitle = "",
    canChangeTariff = false,
    clearPromoFieldError,
    copyText,
    currentLang = "ru",
    currentLanguageOption = null,
    currentTariffName = "",
    devicesBusy = false,
    devicesData = null,
    devicesEnabled = false,
    devicesErrorCode = "",
    devicesIsError = false,
    devicesLoaded = false,
    devicesStatus = "",
    devicesStore,
    emailAuthEnabled = true,
    emailLinkStatus = "",
    goDevices,
    goHome,
    goInvite,
    goSettings,
    goSupport,
    hasActiveTariffSubscription = false,
    hasMultipleTariffs = false,
    hasUnlinkedIdentity = false,
    isAdmin = false,
    languageBusy = false,
    languageClickGuard = false,
    languageClickGuardArmed = false,
    languageMenuOpen = $bindable(false),
    languageOptions = [],
    linkEmailBusy = false,
    linkTelegramAccount,
    linkTelegramAndActivateTrial,
    linkTelegramAndClaimReferralWelcome,
    linkTelegramBusy = false,
    loadDevices,
    openAdminPanel,
    openAppLink,
    openConnectLink,
    openDeviceTopupModal,
    openExternalLink,
    openInstallOrConnect,
    openLinkEmailDialog,
    openPaymentModal,
    openPremiumTopupModal,
    openRegularTopupModal,
    openSetPasswordDialog,
    openTariffChangeModal,
    openTelegramNotificationsBot,
    openTrialInstallOrConnect,
    premiumTrafficTopupBarClickable = false,
    premiumTrafficTopupUnlocked = false,
    primaryPayActionLabel,
    privacyPolicyUrl = "",
    profileAvatarUrl = "",
    profileEmail = "",
    profileTelegramId = "",
    promoBusy = false,
    promoCode = "",
    promoFieldError = "",
    promoIsError = false,
    promoStatus = "",
    referral = {},
    referralBonusDetails = [],
    referralOneBonusPerReferee = false,
    referralWelcomeBonusDays = 0,
    regularTrafficTopupBarClickable = false,
    regularTrafficTopupUnlocked = false,
    screen = "home",
    serverStatusUrl = "",
    setLanguageMenuOpen,
    setPromoCode,
    subscription = {},
    supportEnabled = false,
    supportStore,
    supportUnreadCount = 0,
    supportUnreadLoaded = false,
    supportUnreadLoading = false,
    supportUrl = "",
    t,
    telegramMiniAppContext = false,
    telegramNotificationsNeedPrompt = false,
    telegramNotificationsStartLink = "",
    telegramNotificationsStatus = "unknown",
    telegramPlatform = "",
    telegramProfileName = "",
    termUnitLabel,
    toggleAutoRenew,
    trafficMode = false,
    trialActivationError = "",
    trialActivationResult = null,
    trialBusy = false,
    user = {},
    userAgreementUrl = "",
    userLanguage = "",
  }: Props = $props();
</script>

<WebAppShell
  {screen}
  {activeTab}
  {brandTitle}
  {brand}
  {devicesEnabled}
  {supportEnabled}
  {supportUnreadCount}
  {supportUnreadLoading}
  {supportUnreadLoaded}
  {hasUnlinkedIdentity}
  {isAdmin}
  {openAdminPanel}
  {goDevices}
  {goHome}
  {goInvite}
  {goSupport}
  {goSettings}
  {t}
>
  {#if screen === "home"}
    <HomeScreen
      {appSettings}
      {brand}
      {brandTitle}
      {canChangeTariff}
      {currentTariffName}
      {hasActiveTariffSubscription}
      {hasMultipleTariffs}
      {premiumTrafficTopupBarClickable}
      {premiumTrafficTopupUnlocked}
      {regularTrafficTopupBarClickable}
      {regularTrafficTopupUnlocked}
      {referral}
      {subscription}
      {autoRenewBusy}
      {linkTelegramBusy}
      {telegramNotificationsNeedPrompt}
      {telegramNotificationsStartLink}
      {telegramNotificationsStatus}
      {termUnitLabel}
      {trafficMode}
      {trialBusy}
      {activateTrial}
      {toggleAutoRenew}
      {linkTelegramAndActivateTrial}
      {linkTelegramAndClaimReferralWelcome}
      {openTelegramNotificationsBot}
      openConnectLink={openInstallOrConnect}
      {openPaymentModal}
      {openRegularTopupModal}
      {openPremiumTopupModal}
      {openTariffChangeModal}
      {primaryPayActionLabel}
      {t}
    />
  {:else if screen === "install"}
    <InstallGuideScreen
      {currentLang}
      {telegramPlatform}
      {user}
      {subscription}
      {goHome}
      {openConnectLink}
      {openExternalLink}
      {openAppLink}
      {copyText}
      {t}
    />
  {:else if screen === "trial"}
    <TrialActivationScreen
      {appSettings}
      {brand}
      {brandTitle}
      {subscription}
      {trialBusy}
      {linkTelegramBusy}
      trialResult={trialActivationResult}
      trialError={trialActivationError}
      {activateTrial}
      {linkTelegramAndActivateTrial}
      openInstallOrConnect={openTrialInstallOrConnect}
      {goHome}
      {t}
    />
  {:else if screen === "invite"}
    <InviteScreen
      {referral}
      {referralBonusDetails}
      {referralOneBonusPerReferee}
      {referralWelcomeBonusDays}
      {promoCode}
      {promoFieldError}
      {promoBusy}
      {promoIsError}
      {promoStatus}
      {applyPromo}
      {setPromoCode}
      {clearPromoFieldError}
      {copyText}
      {t}
    />
  {:else if screen === "devices"}
    <DevicesScreen
      {devicesBusy}
      devicesData={devicesData || undefined}
      {devicesIsError}
      {devicesLoaded}
      {devicesErrorCode}
      {devicesStatus}
      {subscription}
      {loadDevices}
      openDeviceDisconnectDialog={devicesStore.openDeviceDisconnectDialog}
      {openDeviceTopupModal}
      {t}
    />
  {:else if screen === "support"}
    {#if supportStore.openedTicketId}
      <SupportTicketScreen
        maxBodyLength={appSettings?.support_ticket_max_body_length || 4000}
        {brand}
        {user}
        userAvatarUrl={profileAvatarUrl}
        userInitials={telegramProfileName ? telegramProfileName.slice(0, 2).toUpperCase() : "U"}
        {t}
      />
    {:else}
      <SupportScreen
        maxSubjectLength={appSettings?.support_ticket_max_subject_length || 160}
        maxBodyLength={appSettings?.support_ticket_max_body_length || 4000}
        {user}
        {t}
      />
    {/if}
  {:else if screen === "settings"}
    <SettingsScreen
      {currentLang}
      {currentLanguageOption}
      {emailAuthEnabled}
      {emailLinkStatus}
      {isAdmin}
      {languageBusy}
      {languageClickGuard}
      {languageClickGuardArmed}
      bind:languageMenuOpen
      {languageOptions}
      {linkEmailBusy}
      {linkTelegramBusy}
      {privacyPolicyUrl}
      {profileAvatarUrl}
      {profileEmail}
      {profileTelegramId}
      {serverStatusUrl}
      {supportUrl}
      {telegramNotificationsNeedPrompt}
      {telegramNotificationsStartLink}
      {telegramNotificationsStatus}
      {telegramProfileName}
      {user}
      {userAgreementUrl}
      {userLanguage}
      showLogout={!telegramMiniAppContext}
      {linkTelegramAccount}
      {openTelegramNotificationsBot}
      logout={accountStore.logout}
      {openAdminPanel}
      {openExternalLink}
      {openLinkEmailDialog}
      {openSetPasswordDialog}
      {setLanguageMenuOpen}
      {t}
      updateAccountLanguage={accountStore.updateAccountLanguage}
    />
  {/if}
</WebAppShell>
