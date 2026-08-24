<script lang="ts">
  import type { AccountStore } from "../lib/webapp/stores/accountStore.js";
  import type { DevicesStore } from "../lib/webapp/stores/devicesStore.js";
  import type { SupportStore } from "../lib/webapp/stores/supportStore.js";
  import type { ApiClient } from "../lib/webapp/publicApi.js";

  import { lazyScreen } from "../lib/webapp/lazyScreen.svelte.js";
  import { resolveProgramEntryPlacement } from "../lib/webapp/programEntryPolicy.js";

  import WebAppShell from "./WebAppShell.svelte";
  import HomeScreen from "./screens/HomeScreen.svelte";
  import ScreenLoading from "./screens/ScreenLoading.svelte";
  import SettingsScreen from "./screens/SettingsScreen.svelte";
  import type {
    AppSettings,
    BooleanAction,
    BrandConfig,
    CopyTextAction,
    DevicesData,
    LanguageOption,
    OpenLinkAction,
    ReferralBonusDetail,
    ReferralState,
    StringAction,
    SubscriptionView,
    TermUnitLabel,
    Translate,
    TrialActivationResult,
    UserProfile,
    VoidAction,
  } from "$lib/webapp/types.js";

  type LoadDevicesAction = (force?: boolean) => void;

  type Props = {
    api: ApiClient["api"];
    accountStore: AccountStore;
    activateTrial: VoidAction;
    activeTab?: string;
    appSettings?: AppSettings;
    applyPromo: VoidAction;
    autoRenewBusy?: boolean;
    brand?: BrandConfig;
    brandTitle?: string;
    canChangeTariff?: boolean;
    clearPromoFieldError: VoidAction;
    copyText: CopyTextAction;
    currentLang?: string;
    currentLanguageOption?: LanguageOption | null;
    currentTariffName?: string;
    devicesBusy?: boolean;
    devicesData?: DevicesData | null;
    devicesEnabled?: boolean;
    devicesErrorCode?: string;
    devicesIsError?: boolean;
    devicesLoaded?: boolean;
    devicesStatus?: string;
    devicesStore: DevicesStore;
    subscriptionReissueEnabled?: boolean;
    subscriptionReissueBusy?: boolean;
    openSubscriptionReissueDialog?: VoidAction;
    emailAuthEnabled?: boolean;
    emailLinkStatus?: string;
    goDevices: VoidAction;
    goHome: VoidAction;
    goInvite: VoidAction;
    goPartner: VoidAction;
    partnerEnabled?: boolean;
    goSettings: VoidAction;
    goSupport: VoidAction;
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
    linkTelegramAccount: VoidAction;
    linkTelegramAndActivateTrial: VoidAction;
    linkTelegramAndClaimReferralWelcome: VoidAction;
    linkTelegramBusy?: boolean;
    loadDevices: LoadDevicesAction;
    openAdminPanel: VoidAction;
    openAppLink: OpenLinkAction;
    openConnectLink: VoidAction;
    openDeviceTopupModal: VoidAction;
    openExternalLink: OpenLinkAction;
    openInstallOrConnect: VoidAction;
    openLinkEmailDialog: VoidAction;
    openPaymentModal: VoidAction;
    openPremiumTopupModal: VoidAction;
    openRegularTopupModal: VoidAction;
    openSetPasswordDialog: VoidAction;
    openTariffChangeModal: VoidAction;
    openTelegramNotificationsBot: VoidAction;
    openTrialInstallOrConnect: VoidAction;
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
    referral?: ReferralState;
    referralBonusDetails?: ReferralBonusDetail[];
    referralOneBonusPerReferee?: boolean;
    referralProgramEnabled?: boolean;
    referralWelcomeBonusDays?: number;
    regularTrafficTopupBarClickable?: boolean;
    regularTrafficTopupUnlocked?: boolean;
    screen?: string;
    serverStatusUrl?: string;
    showTelegramLinkedStatus?: boolean;
    setLanguageMenuOpen: BooleanAction;
    setPromoCode: StringAction;
    subscription?: SubscriptionView;
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
    termUnitLabel: TermUnitLabel;
    toggleAutoRenew: BooleanAction;
    trafficMode?: boolean;
    trialActivationError?: string;
    trialActivationResult?: TrialActivationResult | null;
    trialBusy?: boolean;
    user?: UserProfile;
    userAgreementUrl?: string;
    userLanguage?: string;
  };

  let {
    api,
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
    subscriptionReissueEnabled = false,
    subscriptionReissueBusy = false,
    openSubscriptionReissueDialog = () => {},
    emailAuthEnabled = true,
    emailLinkStatus = "",
    goDevices,
    goHome,
    goInvite,
    goPartner,
    partnerEnabled = false,
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
    referralProgramEnabled = true,
    referralWelcomeBonusDays = 0,
    regularTrafficTopupBarClickable = false,
    regularTrafficTopupUnlocked = false,
    screen = "home",
    serverStatusUrl = "",
    showTelegramLinkedStatus = false,
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

  // Everything past home and settings is fetched when the customer first opens
  // it. Support pulls in the rich text editor, which is by far the heaviest
  // thing the app can load, and most sessions never open any of these tabs.
  const installGuideScreen = lazyScreen(() => import("./screens/InstallGuideScreen.svelte"));
  const trialActivationScreen = lazyScreen(() => import("./screens/TrialActivationScreen.svelte"));
  const inviteScreen = lazyScreen(() => import("./screens/InviteScreen.svelte"));
  const partnerScreen = lazyScreen(() => import("./screens/partner/PartnerScreen.svelte"));
  const devicesScreen = lazyScreen(() => import("./screens/DevicesScreen.svelte"));
  const supportScreen = lazyScreen(() => import("./screens/SupportScreen.svelte"));
  const supportTicketScreen = lazyScreen(() => import("./screens/SupportTicketScreen.svelte"));

  $effect(() => {
    if (screen === "install") installGuideScreen.load();
    else if (screen === "trial") trialActivationScreen.load();
    else if (screen === "invite") inviteScreen.load();
    else if (screen === "partner") partnerScreen.load();
    else if (screen === "devices") devicesScreen.load();
    else if (screen === "support") {
      supportScreen.load();
      if (supportStore.openedTicketId) supportTicketScreen.load();
    }
  });

  // Without the Devices section the reissue action has no home screen, so it
  // moves to Settings.
  const settingsSubscriptionReissueVisible = $derived(
    subscriptionReissueEnabled && !devicesEnabled && Boolean(subscription?.active)
  );
  const programEntryPlacement = $derived(
    resolveProgramEntryPlacement({
      partnerProgramEnabled: partnerEnabled,
      referralProgramEnabled,
    })
  );
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
  {goPartner}
  bonusesNavigationVisible={programEntryPlacement.bonusesNavigationVisible}
  partnerNavigationVisible={programEntryPlacement.partnerNavigationVisible}
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
    {#if installGuideScreen.component}
      {@const Screen = installGuideScreen.component}
      <Screen
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
    {:else}
      <ScreenLoading label={t("wa_loading")} />
    {/if}
  {:else if screen === "trial"}
    {#if trialActivationScreen.component}
      {@const Screen = trialActivationScreen.component}
      <Screen
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
    {:else}
      <ScreenLoading label={t("wa_loading")} />
    {/if}
  {:else if screen === "invite"}
    {#if inviteScreen.component}
      {@const Screen = inviteScreen.component}
      <Screen
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
    {:else}
      <ScreenLoading label={t("wa_loading")} />
    {/if}
  {:else if screen === "partner"}
    {#if partnerScreen.component}
      {@const Screen = partnerScreen.component}
      <Screen {api} {copyText} {t} />
    {:else}
      <ScreenLoading label={t("wa_loading")} />
    {/if}
  {:else if screen === "devices"}
    {#if devicesScreen.component}
      {@const Screen = devicesScreen.component}
      <Screen
        {devicesBusy}
        devicesData={devicesData || undefined}
        {devicesIsError}
        {devicesLoaded}
        {devicesErrorCode}
        {devicesStatus}
        {subscription}
        {loadDevices}
        openDeviceDisconnectDialog={devicesStore.openDeviceDisconnectDialog}
        {subscriptionReissueEnabled}
        {subscriptionReissueBusy}
        {openSubscriptionReissueDialog}
        {openDeviceTopupModal}
        {openPaymentModal}
        {t}
      />
    {:else}
      <ScreenLoading label={t("wa_loading")} />
    {/if}
  {:else if screen === "support"}
    {#if supportStore.openedTicketId}
      {#if supportTicketScreen.component}
        {@const Screen = supportTicketScreen.component}
        <Screen
          maxBodyLength={appSettings?.support_ticket_max_body_length || 4000}
          {brand}
          {user}
          userAvatarUrl={profileAvatarUrl}
          userInitials={telegramProfileName ? telegramProfileName.slice(0, 2).toUpperCase() : "U"}
          {t}
        />
      {:else}
        <ScreenLoading label={t("wa_loading")} />
      {/if}
    {:else if supportScreen.component}
      {@const Screen = supportScreen.component}
      <Screen
        maxSubjectLength={appSettings?.support_ticket_max_subject_length || 160}
        maxBodyLength={appSettings?.support_ticket_max_body_length || 4000}
        {user}
        {t}
      />
    {:else}
      <ScreenLoading label={t("wa_loading")} />
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
      partnerSettingsVisible={programEntryPlacement.partnerSettingsVisible}
      promoActivationVisible={programEntryPlacement.promoSettingsVisible}
      {promoBusy}
      {promoCode}
      {promoFieldError}
      {promoIsError}
      {promoStatus}
      {serverStatusUrl}
      {showTelegramLinkedStatus}
      {subscriptionReissueBusy}
      subscriptionReissueVisible={settingsSubscriptionReissueVisible}
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
      openPartner={goPartner}
      {openExternalLink}
      {openLinkEmailDialog}
      {openSetPasswordDialog}
      {openSubscriptionReissueDialog}
      {applyPromo}
      {clearPromoFieldError}
      {setLanguageMenuOpen}
      {setPromoCode}
      {t}
      updateAccountLanguage={accountStore.updateAccountLanguage}
    />
  {/if}
</WebAppShell>
