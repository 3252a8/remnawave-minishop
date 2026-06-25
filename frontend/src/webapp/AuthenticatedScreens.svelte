<script lang="ts">
  import type { Readable } from "svelte/store";
  import type { LanguageOption } from "../lib/webapp/languageView.js";

  import WebAppShell from "./WebAppShell.svelte";
  import DevicesScreen from "./screens/DevicesScreen.svelte";
  import HomeScreen from "./screens/HomeScreen.svelte";
  import InstallGuideScreen from "./screens/InstallGuideScreen.svelte";
  import InviteScreen from "./screens/InviteScreen.svelte";
  import SettingsScreen from "./screens/SettingsScreen.svelte";
  import SupportScreen from "./screens/SupportScreen.svelte";
  import SupportTicketScreen from "./screens/SupportTicketScreen.svelte";
  import TrialActivationScreen from "./screens/TrialActivationScreen.svelte";

  type AnyRecord = Record<string, any>;
  type StoreLike = Readable<AnyRecord> & Record<string, any>;
  type Action = (...args: any[]) => any;
  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  export let accountStore: StoreLike;
  export let activateTrial: Action;
  export let activeTab = "home";
  export let appSettings: AnyRecord = {};
  export let applyPromo: Action;
  export let autoRenewBusy = false;
  export let brand: AnyRecord = {};
  export let brandTitle = "";
  export let canChangeTariff = false;
  export let clearPromoFieldError: Action;
  export let copyText: Action;
  export let currentLang = "ru";
  export let currentLanguageOption: LanguageOption | null = null;
  export let currentTariffName = "";
  export let devicesBusy = false;
  export let devicesData: AnyRecord | null = null;
  export let devicesEnabled = false;
  export let devicesErrorCode = "";
  export let devicesIsError = false;
  export let devicesLoaded = false;
  export let devicesStatus = "";
  export let devicesStore: StoreLike;
  export let emailAuthEnabled = true;
  export let emailLinkStatus = "";
  export let goDevices: Action;
  export let goHome: Action;
  export let goInvite: Action;
  export let goSettings: Action;
  export let goSupport: Action;
  export let hasActiveTariffSubscription = false;
  export let hasMultipleTariffs = false;
  export let hasUnlinkedIdentity = false;
  export let isAdmin = false;
  export let languageBusy = false;
  export let languageClickGuard = false;
  export let languageClickGuardArmed = false;
  export let languageMenuOpen = false;
  export let languageOptions: LanguageOption[] = [];
  export let linkEmailBusy = false;
  export let linkTelegramAccount: Action;
  export let linkTelegramAndActivateTrial: Action;
  export let linkTelegramAndClaimReferralWelcome: Action;
  export let linkTelegramBusy = false;
  export let loadDevices: Action;
  export let openAdminPanel: Action;
  export let openAppLink: Action;
  export let openConnectLink: Action;
  export let openDeviceTopupModal: Action;
  export let openExternalLink: Action;
  export let openInstallOrConnect: Action;
  export let openLinkEmailDialog: Action;
  export let openPaymentModal: Action;
  export let openPremiumTopupModal: Action;
  export let openRegularTopupModal: Action;
  export let openSetPasswordDialog: Action;
  export let openTariffChangeModal: Action;
  export let openTelegramNotificationsBot: Action;
  export let openTrialInstallOrConnect: Action;
  export let premiumTrafficTopupBarClickable = false;
  export let premiumTrafficTopupUnlocked = false;
  export let primaryPayActionLabel: () => string;
  export let privacyPolicyUrl = "";
  export let profileAvatarUrl = "";
  export let profileEmail = "";
  export let profileTelegramId = "";
  export let promoBusy = false;
  export let promoCode = "";
  export let promoFieldError = "";
  export let promoIsError = false;
  export let promoStatus = "";
  export let referral: AnyRecord = {};
  export let referralBonusDetails: AnyRecord[] = [];
  export let referralOneBonusPerReferee = false;
  export let referralWelcomeBonusDays = 0;
  export let regularTrafficTopupBarClickable = false;
  export let regularTrafficTopupUnlocked = false;
  export let screen = "home";
  export let serverStatusUrl = "";
  export let setLanguageMenuOpen: (open: boolean) => void;
  export let setPromoCode: (value: string) => void;
  export let subscription: AnyRecord = {};
  export let supportEnabled = false;
  export let supportStore: StoreLike;
  export let supportUnreadCount = 0;
  export let supportUnreadLoaded = false;
  export let supportUnreadLoading = false;
  export let supportUrl = "";
  export let t: Translate;
  export let telegramMiniAppContext = false;
  export let telegramNotificationsNeedPrompt = false;
  export let telegramNotificationsStartLink = "";
  export let telegramNotificationsStatus = "unknown";
  export let telegramPlatform = "";
  export let telegramProfileName = "";
  export let termUnitLabel: Action;
  export let toggleAutoRenew: Action;
  export let trafficMode = false;
  export let trialActivationError = "";
  export let trialActivationResult: AnyRecord | null = null;
  export let trialBusy = false;
  export let user: AnyRecord = {};
  export let userAgreementUrl = "";
  export let userLanguage = "";
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
      setPromoCode={setPromoCode as any}
      {clearPromoFieldError}
      copyText={copyText as any}
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
    {#if $supportStore.openedTicketId}
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
