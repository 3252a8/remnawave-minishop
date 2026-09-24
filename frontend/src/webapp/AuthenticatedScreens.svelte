<script lang="ts">
  import { giftState } from "$lib/webapp/gifts.svelte.js";
  import type { ThemeOption } from "$lib/webapp/themePreference.js";
  import type { AccountStore } from "../lib/webapp/stores/accountStore.js";
  import type { DevicesStore } from "../lib/webapp/stores/devicesStore.js";
  import type { SupportStore } from "../lib/webapp/stores/supportStore.js";
  import type { ServerStatusStore } from "../lib/webapp/stores/serverStatusStore.svelte.js";
  import type { ApiClient } from "../lib/webapp/publicApi.js";

  import { lazyScreen } from "../lib/webapp/lazyScreen.svelte.js";
  import { visibleMenuButtons } from "../lib/webapp/menuButtons.js";
  import { resolveProgramEntryPlacement } from "../lib/webapp/programEntryPolicy.js";
  import {
    DEFAULT_HOME_ELEMENT_VISIBILITY,
    type HomeElementVisibility,
    type ReferralBonusListMode,
  } from "../lib/webapp/themeStyle.js";

  import UserExtensions from "./extensions/UserExtensions.svelte";
  import type { UserNavigationItem } from "$lib/webapp/extensionHost";
  import WebAppShell from "./WebAppShell.svelte";
  import HomeScreen from "./screens/HomeScreen.svelte";
  import ScreenLoading from "./screens/ScreenLoading.svelte";
  import SettingsScreen from "./screens/SettingsScreen.svelte";
  import NotificationSettingsScreen from "./screens/NotificationSettingsScreen.svelte";
  import SecurityScreen from "./screens/SecurityScreen.svelte";
  import BalanceTopupDialog from "./payment-dialogs/BalanceTopupDialog.svelte";
  import type {
    AppSettings,
    BalanceView,
    BooleanAction,
    BrandConfig,
    CopyTextAction,
    DevicesData,
    LanguageOption,
    MenuButtonView,
    OpenLinkAction,
    PaymentMethodView,
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
    apiClient?: ApiClient;
    routePrefix?: string;
    api: ApiClient["api"];
    accountStore: AccountStore;
    activateTrial: VoidAction;
    activeTab?: string;
    appSettings?: AppSettings;
    balance?: BalanceView;
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
    notificationPreferencesEnabled?: boolean;
    goDevices: VoidAction;
    goHome: VoidAction;
    goInvite: VoidAction;
    goInstall: VoidAction;
    goPartner: VoidAction;
    partnerEnabled?: boolean;
    goSettings: VoidAction;
    goNotifications: VoidAction;
    goSecurity: VoidAction;
    goTrial: VoidAction;
    goStatus: (parent?: "home" | "settings") => void;
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
    methods?: PaymentMethodView[];
    paymentMethodsDisplayMode?: "dropdown" | "buttons" | string;
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
    referralBonusListMode?: ReferralBonusListMode;
    homeElementVisibility?: HomeElementVisibility;
    referralOneBonusPerReferee?: boolean;
    referralProgramEnabled?: boolean;
    referralWelcomeBonusDays?: number;
    regularTrafficTopupBarClickable?: boolean;
    regularTrafficTopupUnlocked?: boolean;
    screen?: string;
    serverStatusInternal?: boolean;
    serverStatusShowOnHome?: boolean;
    compactHomeEnabled?: boolean;
    serverStatusUrl?: string;
    statusStore: ServerStatusStore;
    setLanguageMenuOpen: BooleanAction;
    setPromoCode: StringAction;
    subscription?: SubscriptionView;
    supportEnabled?: boolean;
    supportStore: SupportStore;
    supportUnreadCount?: number;
    supportUnreadLoaded?: boolean;
    supportUnreadLoading?: boolean;
    supportUrl?: string;
    themeOptions?: ThemeOption[];
    themePreference?: string;
    themeSwitcherVisible?: boolean;
    setThemePreference?: StringAction;
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
    apiClient,
    routePrefix = "",
    api,
    accountStore,
    activateTrial,
    activeTab = "home",
    appSettings = {},
    balance = {} as BalanceView,
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
    notificationPreferencesEnabled = true,
    goDevices,
    goHome,
    goInvite,
    goInstall,
    goPartner,
    partnerEnabled = false,
    goSettings,
    goNotifications,
    goSecurity,
    goTrial,
    goStatus,
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
    methods = [],
    paymentMethodsDisplayMode = "dropdown",
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
    referralBonusListMode = "plain",
    homeElementVisibility = DEFAULT_HOME_ELEMENT_VISIBILITY,
    referralOneBonusPerReferee = false,
    referralProgramEnabled = true,
    referralWelcomeBonusDays = 0,
    regularTrafficTopupBarClickable = false,
    regularTrafficTopupUnlocked = false,
    screen = "home",
    serverStatusInternal = false,
    serverStatusShowOnHome = false,
    compactHomeEnabled = false,
    serverStatusUrl = "",
    statusStore,
    setLanguageMenuOpen,
    setPromoCode,
    subscription = {},
    supportEnabled = false,
    supportStore,
    supportUnreadCount = 0,
    supportUnreadLoaded = false,
    supportUnreadLoading = false,
    supportUrl = "",
    themeOptions = [],
    themePreference = "auto",
    themeSwitcherVisible = false,
    setThemePreference = () => {},
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
  const statusScreen = lazyScreen(() => import("./screens/StatusScreen.svelte"));

  $effect(() => {
    if (screen === "install") installGuideScreen.load();
    else if (screen === "trial") trialActivationScreen.load();
    else if (screen === "invite") inviteScreen.load();
    else if (screen === "partner") partnerScreen.load();
    else if (screen === "devices") devicesScreen.load();
    else if (screen === "support") {
      supportScreen.load();
      if (supportStore.openedTicketId) supportTicketScreen.load();
    } else if (screen === "status") statusScreen.load();
  });

  const programEntryPlacement = $derived(
    resolveProgramEntryPlacement({
      partnerProgramEnabled: partnerEnabled,
      referralProgramEnabled,
      giftsAvailable:
        appSettings?.gifts_enabled === true ||
        giftState.enabled ||
        giftState.gifts.length > 0 ||
        Boolean(giftState.token || giftState.pending),
    })
  );
  const menuButtons = $derived(
    visibleMenuButtons(
      Array.isArray(appSettings?.menu_buttons)
        ? (appSettings.menu_buttons as MenuButtonView[])
        : [],
      telegramMiniAppContext
    )
  );
  let balanceTopupOpen = $state(false);

  function openMenuButton(button: MenuButtonView): void {
    if (button.kind !== "webapp") {
      openExternalLink(String(button.target || ""));
      return;
    }
    switch (button.target) {
      case "plans":
        openPaymentModal();
        break;
      case "install":
        goInstall();
        break;
      case "trial":
        goTrial();
        break;
      case "invite":
        goInvite();
        break;
      case "partner":
        goPartner();
        break;
      case "devices":
        goDevices();
        break;
      case "support":
        goSupport();
        break;
      case "settings":
        goSettings();
        break;
      case "notifications":
        goNotifications();
        break;
      case "status":
        goStatus("settings");
        break;
      default:
        goHome();
    }
  }
  let extensionNavigation = $state<UserNavigationItem[]>([]);
</script>

<WebAppShell
  {extensionNavigation}
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
  partnerSettingsVisible={programEntryPlacement.partnerSettingsVisible}
  {goSupport}
  {goSettings}
  {goNotifications}
  {goSecurity}
  {t}
>
  {#if screen === "home"}
    <HomeScreen
      {appSettings}
      {balance}
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
      openBalanceTopup={() => (balanceTopupOpen = true)}
      {openRegularTopupModal}
      {openPremiumTopupModal}
      {openTariffChangeModal}
      {goSecurity}
      goStatus={() => goStatus("home")}
      {openExternalLink}
      {serverStatusShowOnHome}
      {compactHomeEnabled}
      {homeElementVisibility}
      {statusStore}
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
        openSecurity={goSecurity}
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
        {referralProgramEnabled}
        {referralBonusDetails}
        {referralBonusListMode}
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
      <Screen {api} {copyText} goBack={activeTab === "settings" ? goSettings : undefined} {t} />
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
      {notificationPreferencesEnabled}
      {isAdmin}
      {languageBusy}
      {languageClickGuard}
      {languageClickGuardArmed}
      bind:languageMenuOpen
      {languageOptions}
      {menuButtons}
      {privacyPolicyUrl}
      {profileAvatarUrl}
      {profileEmail}
      {profileTelegramId}
      {balance}
      partnerSettingsVisible={programEntryPlacement.partnerSettingsVisible}
      promoActivationVisible={programEntryPlacement.promoSettingsVisible}
      {promoBusy}
      {promoCode}
      {promoFieldError}
      {promoIsError}
      {promoStatus}
      {serverStatusUrl}
      {serverStatusInternal}
      {supportUrl}
      {themeOptions}
      {themePreference}
      {themeSwitcherVisible}
      {setThemePreference}
      {telegramNotificationsNeedPrompt}
      {telegramNotificationsStartLink}
      {telegramNotificationsStatus}
      {telegramProfileName}
      {userAgreementUrl}
      {userLanguage}
      {hasUnlinkedIdentity}
      showLogout={!telegramMiniAppContext}
      {openTelegramNotificationsBot}
      logout={accountStore.logout}
      {openAdminPanel}
      openPartner={goPartner}
      {openExternalLink}
      openBalanceTopup={() => (balanceTopupOpen = true)}
      {openMenuButton}
      openNotifications={goNotifications}
      openSecurity={goSecurity}
      openServerStatus={() => goStatus("settings")}
      {applyPromo}
      {clearPromoFieldError}
      {setLanguageMenuOpen}
      {setPromoCode}
      {t}
      updateAccountLanguage={accountStore.updateAccountLanguage}
    />
  {:else if screen === "notifications" && notificationPreferencesEnabled}
    <NotificationSettingsScreen {api} {emailAuthEnabled} {goSettings} {t} {user} />
  {:else if screen === "security"}
    <SecurityScreen
      {api}
      authProviders={(appSettings.auth_providers || appSettings.authProviders || []) as string[]}
      {brandTitle}
      {currentLang}
      {emailAuthEnabled}
      emailChangeEnabled={Boolean(appSettings.email_address_change_enabled ?? true)}
      {goSettings}
      linkTelegramAccount={accountStore.linkTelegramFromSettings}
      {openLinkEmailDialog}
      {openSetPasswordDialog}
      {subscriptionReissueBusy}
      subscriptionReissueVisible={subscriptionReissueEnabled && Boolean(subscription?.active)}
      {openSubscriptionReissueDialog}
      {t}
      {telegramMiniAppContext}
      {user}
    />
  {:else if screen === "status"}
    {#if statusScreen.component}
      {@const Screen = statusScreen.component}
      <Screen
        {currentLang}
        {statusStore}
        goHome={activeTab === "settings" ? goSettings : goHome}
        {openExternalLink}
        {t}
      />
    {:else}
      <ScreenLoading label={t("wa_loading")} />
    {/if}
  {/if}
  {#if balance.enabled}
    <BalanceTopupDialog
      {api}
      bind:open={balanceTopupOpen}
      {balance}
      {methods}
      {paymentMethodsDisplayMode}
      {openExternalLink}
      {t}
    />
  {/if}
  {#if apiClient}
    <UserExtensions
      client={apiClient}
      {screen}
      language={currentLang}
      {t}
      {routePrefix}
      context={{ screen, subscription }}
      bind:navigation={extensionNavigation}
    />
  {/if}
</WebAppShell>
