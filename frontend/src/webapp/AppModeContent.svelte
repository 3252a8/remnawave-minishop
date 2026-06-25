<script lang="ts">
  import type { Readable, Writable } from "svelte/store";

  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import type { AppActionRuntime } from "../lib/webapp/appActionRuntime.js";
  import type { AppShellView } from "../lib/webapp/appShellView.js";
  import type { LanguageOption } from "../lib/webapp/languageView.js";
  import AppLaunchScreen from "./screens/AppLaunchScreen.svelte";
  import AuthenticatedDialogs from "./AuthenticatedDialogs.svelte";
  import AuthenticatedScreens from "./AuthenticatedScreens.svelte";
  import AuthScreen from "./auth/AuthScreen.svelte";
  import InstallGuideScreen from "./screens/InstallGuideScreen.svelte";

  type AnyRecord = Record<string, any>;
  type ReadableStoreLike = Readable<AnyRecord> & Record<string, any>;
  type WritableStoreLike = Writable<AnyRecord> & Record<string, any>;
  type Action = (...args: any[]) => any;
  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  const noopAction: Action = () => {};
  const noopPrimaryPayActionLabel = () => "";

  export let accountStore: WritableStoreLike;
  export let shellView: AppShellView | null = null;
  export let appActions: AppActionRuntime | null = null;
  export let actionsStore: ReadableStoreLike;
  export let activateTrial: Action = noopAction;
  export let activationSuccessDialogOpen = false;
  export let activationSuccessUseInstallGuides = false;
  export let activeTab = "home";
  export let adminBundleApi: AnyRecord | null = null;
  export let adminBundleError = "";
  export let adminMountTarget: HTMLElement | null = null;
  export let appLaunchTarget = "";
  export let appSettings: AnyRecord = {};
  export let applyPromo: Action = noopAction;
  export let authBusy = false;
  export let authIsError = false;
  export let authResendCooldown = 0;
  export let authStatus = "";
  export let authStore: WritableStoreLike;
  export let autoRenewBusy = false;
  export let backToTariffList: Action = noopAction;
  export let billingStore: WritableStoreLike;
  export let brand: AnyRecord = {};
  export let brandTitle = "";
  export let canChangeTariff = false;
  export let cfg: AnyRecord = {};
  export let clearPromoFieldError: Action = noopAction;
  export let closeActivationSuccessDialog: Action = noopAction;
  export let closeDeviceTopupModal: Action = noopAction;
  export let continueWithSelectedTariff: Action = noopAction;
  export let copyText: Action = noopAction;
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
  export let devicesStore: WritableStoreLike;
  export let disconnectDevice: Action = noopAction;
  export let emailAuthEnabled = true;
  export let emailLinkStatus = "";
  export let goDevices: Action = noopAction;
  export let goHome: Action = noopAction;
  export let goInvite: Action = noopAction;
  export let goSettings: Action = noopAction;
  export let goSupport: Action = noopAction;
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
  export let linkTelegramAndActivateTrial: Action = noopAction;
  export let linkTelegramAndClaimReferralWelcome: Action = noopAction;
  export let linkTelegramBusy = false;
  export let loadDevices: Action = noopAction;
  export let loginEmailFieldError = "";
  export let loginEmailTooltipOpen = false;
  export let methods: AnyRecord[] = [];
  export let mode = "loading";
  export let openAdminPanel: Action = noopAction;
  export let openAppLaunchTarget: Action = noopAction;
  export let openAppLink: Action = noopAction;
  export let openConnectLink: Action = noopAction;
  export let openDeviceTopupModal: Action = noopAction;
  export let openExternalLink: Action = noopAction;
  export let openInstallOrConnect: Action = noopAction;
  export let openLoginTelegram: Action = noopAction;
  export let openPaymentModal: Action = noopAction;
  export let openPremiumTopupModal: Action = noopAction;
  export let openPublicConnectLink: Action = noopAction;
  export let openRegularTopupModal: Action = noopAction;
  export let openSettingsLinkEmailDialog: Action = noopAction;
  export let openSettingsSetPasswordDialog: Action = noopAction;
  export let openTariffChangeModal: Action = noopAction;
  export let openTelegramNotificationsBot: Action = noopAction;
  export let openTrialInstallOrConnect: Action = noopAction;
  export let passwordLoginFallback = false;
  export let passwordLoginMode = false;
  export let pendingEmail = "";
  export let plans: AnyRecord[] = [];
  export let premiumTrafficTopupBarClickable = false;
  export let premiumTrafficTopupUnlocked = false;
  export let primaryPayActionLabel: () => string = noopPrimaryPayActionLabel;
  export let privacyPolicyUrl = "";
  export let profileAvatarUrl = "";
  export let profileEmail = "";
  export let profileTelegramId = "";
  export let promoBusy = false;
  export let promoCode = "";
  export let promoFieldError = "";
  export let promoIsError = false;
  export let promoStatus = "";
  export let publicInstallSubscription: AnyRecord | null = null;
  export let publicInstallToken = "";
  export let referral: AnyRecord = {};
  export let referralBonusDetails: AnyRecord[] = [];
  export let referralOneBonusPerReferee = false;
  export let referralWelcomeBonusDays = 0;
  export let refreshAppLaunchTarget: Action = noopAction;
  export let regularTrafficTopupBarClickable = false;
  export let regularTrafficTopupUnlocked = false;
  export let screen = "home";
  export let selectedTariff: AnyRecord | null = null;
  export let selectedTariffPlans: AnyRecord[] = [];
  export let selectTariff: Action = noopAction;
  export let serverStatusUrl = "";
  export let setLanguageMenuOpen: (open: boolean) => void;
  export let setPasswordLoginMode: (enabled: boolean) => void;
  export let setPromoCode: (value: string) => void = noopAction;
  export let shellStyle = "";
  export let shellThemeClass = "";
  export let shellToneClass = "";
  export let singleTariffMode = false;
  export let submitEmailOnEnter: Action = noopAction;
  export let subscription: AnyRecord = {};
  export let subscriptionPurchaseDescription = "";
  export let supportEnabled = false;
  export let supportStore: ReadableStoreLike;
  export let supportUnreadCount = 0;
  export let supportUnreadLoaded = false;
  export let supportUnreadLoading = false;
  export let supportUrl = "";
  export let t: Translate;
  export let tariffCatalog: AnyRecord[] = [];
  export let tariffMode = false;
  export let telegramLoginBusy = false;
  export let telegramLoginChecking = false;
  export let telegramLoginLabel = "";
  export let telegramLoginUnavailable = false;
  export let telegramLoginUnavailableMessage = "";
  export let telegramMiniAppContext = false;
  export let telegramNotificationsNeedPrompt = false;
  export let telegramNotificationsStartLink = "";
  export let telegramNotificationsStatus = "unknown";
  export let telegramPlatform = "";
  export let telegramProfileName = "";
  export let termUnitLabel: Action = noopAction;
  export let toggleAutoRenew: Action = noopAction;
  export let trafficMode = false;
  export let trialActivationError = "";
  export let trialActivationResult: AnyRecord | null = null;
  export let trialBusy = false;
  export let user: AnyRecord = {};
  export let userAgreementUrl = "";
  export let userLanguage = "";
  export let updateGuestLanguage: (language: string) => void;

  $: ({
    authStatus,
    authIsError,
    authBusy,
    telegramLoginBusy,
    loginEmailFieldError,
    loginEmailTooltipOpen,
    passwordLoginFallback,
    passwordLoginMode,
    authResendCooldown,
    pendingEmail,
  } = $authStore);
  $: ({ devicesData, devicesLoaded, devicesBusy, devicesStatus, devicesIsError, devicesErrorCode } =
    $devicesStore);
  $: ({
    unreadCount: supportUnreadCount,
    unreadLoading: supportUnreadLoading,
    unreadLoaded: supportUnreadLoaded,
  } = $supportStore);
  $: ({ linkEmailBusy, linkTelegramBusy } = $accountStore);
  $: ({
    promoCode,
    promoBusy,
    promoStatus,
    promoIsError,
    promoFieldError,
    trialBusy,
    trialActivationResult,
    trialActivationError,
  } = $actionsStore);

  $: if (shellView) {
    ({
      accountView: {
        emailLinkStatus,
        hasUnlinkedIdentity,
        privacyPolicyUrl,
        profileAvatarUrl,
        profileEmail,
        profileTelegramId,
        serverStatusUrl,
        supportUrl,
        telegramNotificationsNeedPrompt,
        telegramNotificationsStartLink,
        telegramNotificationsStatus,
        telegramProfileName,
        userAgreementUrl,
      },
      appDataView: {
        appSettings,
        brand,
        brandTitle,
        devicesEnabled,
        emailAuthEnabled,
        methods,
        plans,
        referral,
        referralBonusDetails,
        referralOneBonusPerReferee,
        referralWelcomeBonusDays,
        subscription,
        subscriptionPurchaseDescription,
        supportEnabled,
      },
      billingView: {
        canChangeTariff,
        currentTariffName,
        hasActiveTariffSubscription,
        hasMultipleTariffs,
        premiumTrafficTopupBarClickable,
        premiumTrafficTopupUnlocked,
        regularTrafficTopupBarClickable,
        regularTrafficTopupUnlocked,
        selectedTariff,
        selectedTariffPlans,
        singleTariffMode,
        tariffCatalog,
        tariffMode,
        trafficMode,
      },
      currentLang,
      isAdmin,
      languageView: { currentLanguageOption = null, languageOptions },
      telegramLoginView: {
        telegramLoginChecking,
        telegramLoginLabel,
        telegramLoginUnavailable,
        telegramLoginUnavailableMessage,
      },
      telegramMiniAppContext,
      themeView: { shellStyle, shellThemeClass, shellToneClass },
      user,
      userLanguage,
    } = shellView);
  }

  $: if (appActions) {
    ({
      activateTrial,
      applyPromo,
      backToTariffList,
      clearPromoFieldError,
      closeDeviceTopupModal,
      continueWithSelectedTariff,
      copyText,
      disconnectDevice,
      goDevices,
      goHome,
      goInvite,
      goSettings,
      goSupport,
      linkTelegramAndActivateTrial,
      linkTelegramAndClaimReferralWelcome,
      loadDevices,
      openAdminPanel,
      openAppLaunchTarget,
      openAppLink,
      openConnectLink,
      openDeviceTopupModal,
      openExternalLink,
      openInstallOrConnect,
      openLoginTelegram,
      openPaymentModal,
      openPremiumTopupModal,
      openPublicConnectLink,
      openRegularTopupModal,
      openSettingsLinkEmailDialog,
      openSettingsSetPasswordDialog,
      openTariffChangeModal,
      openTelegramNotificationsBot,
      openTrialInstallOrConnect,
      primaryPayActionLabel,
      refreshAppLaunchTarget,
      selectTariff,
      setPromoCode,
      toggleAutoRenew,
    } = appActions);
  }
</script>

<div class="app-shell {shellToneClass} {shellThemeClass}" style={shellStyle}>
  {#if mode === "loading"}
    <div class="loader">
      <BrandMark {brand} size="md" />
      <div>{t("wa_loading")}</div>
    </div>
  {:else if mode === "appLaunch"}
    <AppLaunchScreen {brand} {appLaunchTarget} {refreshAppLaunchTarget} {openAppLaunchTarget} {t} />
  {:else if mode === "publicInstall"}
    <div class="public-install-shell">
      <a class="public-install-brand" href="/" aria-label={brandTitle}>
        <BrandMark {brand} />
        <strong>{brandTitle}</strong>
      </a>
      <InstallGuideScreen
        {currentLang}
        {telegramPlatform}
        user={{}}
        subscription={publicInstallSubscription || {
          install_share_token: publicInstallToken,
        }}
        {goHome}
        openConnectLink={openPublicConnectLink}
        {openExternalLink}
        {openAppLink}
        {copyText}
        {t}
        publicMode
      />
    </div>
  {:else if mode === "login"}
    <AuthScreen
      {screen}
      CFG={cfg}
      {brandTitle}
      {brand}
      bind:email={$authStore.email}
      bind:emailPassword={$authStore.emailPassword}
      bind:emailCode={$authStore.emailCode}
      {pendingEmail}
      {authStatus}
      {authIsError}
      {authBusy}
      {authResendCooldown}
      {loginEmailFieldError}
      {loginEmailTooltipOpen}
      {passwordLoginFallback}
      {passwordLoginMode}
      {telegramLoginBusy}
      {telegramLoginUnavailable}
      {telegramLoginChecking}
      {telegramLoginLabel}
      {telegramLoginUnavailableMessage}
      {privacyPolicyUrl}
      {userAgreementUrl}
      {currentLang}
      {currentLanguageOption}
      {languageOptions}
      {languageMenuOpen}
      {languageClickGuard}
      {languageClickGuardArmed}
      {t}
      {setLanguageMenuOpen}
      updateLoginLanguage={updateGuestLanguage}
      requestEmailCode={() =>
        authStore.requestEmailCode((nextScreen: string) => (screen = nextScreen))}
      loginWithEmailPassword={authStore.loginWithEmailPassword}
      verifyEmailCode={authStore.verifyEmailCode}
      openTelegramLogin={openLoginTelegram}
      {openExternalLink}
      {submitEmailOnEnter}
      onBackToLogin={() => (screen = "login")}
      clearLoginEmailError={() => {
        loginEmailFieldError = "";
        loginEmailTooltipOpen = false;
      }}
      setPasswordLoginMode={(enabled: boolean) => setPasswordLoginMode(enabled)}
    />
  {:else if screen === "admin" && isAdmin}
    {#if adminBundleApi}
      <div class="admin-mount" bind:this={adminMountTarget}></div>
    {:else}
      <div class="loader">
        <BrandMark {brand} size="md" />
        <div>{adminBundleError ? t("wa_unavailable") : t("wa_loading")}</div>
      </div>
    {/if}
  {:else}
    <AuthenticatedScreens
      {accountStore}
      {activateTrial}
      {activeTab}
      {appSettings}
      {applyPromo}
      {autoRenewBusy}
      {brand}
      {brandTitle}
      {canChangeTariff}
      {clearPromoFieldError}
      {copyText}
      {currentLang}
      {currentLanguageOption}
      {currentTariffName}
      {devicesBusy}
      {devicesData}
      {devicesEnabled}
      {devicesErrorCode}
      {devicesIsError}
      {devicesLoaded}
      {devicesStatus}
      {devicesStore}
      {emailAuthEnabled}
      {emailLinkStatus}
      {goDevices}
      {goHome}
      {goInvite}
      {goSettings}
      {goSupport}
      {hasActiveTariffSubscription}
      {hasMultipleTariffs}
      {hasUnlinkedIdentity}
      {isAdmin}
      {languageBusy}
      {languageClickGuard}
      {languageClickGuardArmed}
      bind:languageMenuOpen
      {languageOptions}
      {linkEmailBusy}
      linkTelegramAccount={accountStore.linkTelegramFromSettings}
      {linkTelegramAndActivateTrial}
      {linkTelegramAndClaimReferralWelcome}
      {linkTelegramBusy}
      {loadDevices}
      {openAdminPanel}
      {openAppLink}
      {openConnectLink}
      {openDeviceTopupModal}
      {openExternalLink}
      {openInstallOrConnect}
      openLinkEmailDialog={openSettingsLinkEmailDialog}
      {openPaymentModal}
      {openPremiumTopupModal}
      {openRegularTopupModal}
      openSetPasswordDialog={openSettingsSetPasswordDialog}
      {openTariffChangeModal}
      {openTelegramNotificationsBot}
      {openTrialInstallOrConnect}
      {premiumTrafficTopupBarClickable}
      {premiumTrafficTopupUnlocked}
      {primaryPayActionLabel}
      {privacyPolicyUrl}
      {profileAvatarUrl}
      {profileEmail}
      {profileTelegramId}
      {promoBusy}
      {promoCode}
      {promoFieldError}
      {promoIsError}
      {promoStatus}
      {referral}
      {referralBonusDetails}
      {referralOneBonusPerReferee}
      {referralWelcomeBonusDays}
      {regularTrafficTopupBarClickable}
      {regularTrafficTopupUnlocked}
      {screen}
      {serverStatusUrl}
      {setLanguageMenuOpen}
      {setPromoCode}
      {subscription}
      {supportEnabled}
      {supportStore}
      {supportUnreadCount}
      {supportUnreadLoaded}
      {supportUnreadLoading}
      {supportUrl}
      {t}
      {telegramMiniAppContext}
      {telegramNotificationsNeedPrompt}
      {telegramNotificationsStartLink}
      {telegramNotificationsStatus}
      {telegramPlatform}
      {telegramProfileName}
      {termUnitLabel}
      {toggleAutoRenew}
      {trafficMode}
      {trialActivationError}
      {trialActivationResult}
      {trialBusy}
      {user}
      {userAgreementUrl}
      {userLanguage}
    />

    <AuthenticatedDialogs
      {accountStore}
      {activationSuccessDialogOpen}
      {activationSuccessUseInstallGuides}
      {backToTariffList}
      {billingStore}
      {closeActivationSuccessDialog}
      {closeDeviceTopupModal}
      {continueWithSelectedTariff}
      {devicesStore}
      {disconnectDevice}
      {emailAuthEnabled}
      {hasMultipleTariffs}
      {methods}
      {plans}
      {selectTariff}
      {selectedTariff}
      {selectedTariffPlans}
      {singleTariffMode}
      {subscription}
      {subscriptionPurchaseDescription}
      {t}
      {tariffCatalog}
      {tariffMode}
      {termUnitLabel}
      {trafficMode}
      {user}
    />
  {/if}
</div>
