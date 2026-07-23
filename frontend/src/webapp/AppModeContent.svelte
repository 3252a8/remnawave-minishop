<script lang="ts">
  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import type { AppActionRuntime } from "../lib/webapp/appActionRuntime.js";
  import type { AppShellView } from "../lib/webapp/appShellView.js";
  import type { AccountStore } from "../lib/webapp/stores/accountStore.js";
  import type { ActionsStore } from "../lib/webapp/stores/actionsStore.js";
  import type { AuthStore } from "../lib/webapp/stores/authStore.js";
  import type { BillingStore } from "../lib/webapp/stores/billingStore.js";
  import type { DevicesStore } from "../lib/webapp/stores/devicesStore.js";
  import type { SupportStore } from "../lib/webapp/stores/supportStore.js";
  import AppLaunchScreen from "./screens/AppLaunchScreen.svelte";
  import AuthenticatedDialogs from "./AuthenticatedDialogs.svelte";
  import AuthenticatedScreens from "./AuthenticatedScreens.svelte";
  import AuthScreen from "./auth/AuthScreen.svelte";
  import InstallGuideScreen from "./screens/InstallGuideScreen.svelte";
  import {
    type BooleanAction,
    type StringAction,
    type SubscriptionView,
    type TermUnitLabel,
    type Translate,
    type VoidAction,
    type WebappConfig,
    type WebappRecord,
  } from "$lib/webapp/types.js";

  type SubmitEmailOnEnterAction = (event: KeyboardEvent) => void;

  type AppModeStores = {
    accountStore: AccountStore;
    actionsStore: ActionsStore;
    authStore: AuthStore;
    billingStore: BillingStore;
    devicesStore: DevicesStore;
    supportStore: SupportStore;
  };

  type AppModeViewState = {
    activationSuccessDialogOpen: boolean;
    activationSuccessUseInstallGuides: boolean;
    activeTab: string;
    adminBundleApi: WebappRecord | null;
    adminBundleError: string;
    appLaunchTarget: string;
    autoRenewBusy: boolean;
    subscriptionReissueDialogOpen: boolean;
    subscriptionReissueBusy: boolean;
    cfg: WebappConfig;
    languageBusy: boolean;
    languageClickGuard: boolean;
    languageClickGuardArmed: boolean;
    mode: string;
    publicInstallSubscription: SubscriptionView | null;
    publicInstallToken: string;
    telegramPlatform: string;
  };

  type AppModeControls = {
    closeActivationSuccessDialog: VoidAction;
    setLanguageMenuOpen: BooleanAction;
    setPasswordLoginMode: BooleanAction;
    submitEmailOnEnter: SubmitEmailOnEnterAction;
    t: Translate;
    termUnitLabel: TermUnitLabel;
    updateGuestLanguage: StringAction;
  };

  type Props = {
    stores: AppModeStores;
    shellView: AppShellView;
    appActions: AppActionRuntime;
    viewState: AppModeViewState;
    controls: AppModeControls;
    adminMountTarget?: HTMLElement | null;
    languageMenuOpen?: boolean;
    screen?: string;
  };

  let {
    stores,
    shellView,
    appActions,
    viewState,
    controls,
    adminMountTarget = $bindable(null),
    languageMenuOpen = $bindable(false),
    screen = $bindable("home"),
  }: Props = $props();

  const accountStore = $derived(stores.accountStore);
  const actionsStore = $derived(stores.actionsStore);
  const authStore = $derived(stores.authStore);
  const billingStore = $derived(stores.billingStore);
  const devicesStore = $derived(stores.devicesStore);
  const supportStore = $derived(stores.supportStore);

  const closeActivationSuccessDialog = $derived(controls.closeActivationSuccessDialog);
  const setLanguageMenuOpen = $derived(controls.setLanguageMenuOpen);
  const setPasswordLoginMode = $derived(controls.setPasswordLoginMode);
  const submitEmailOnEnter = $derived(controls.submitEmailOnEnter);
  const t = $derived(controls.t);
  const termUnitLabel = $derived(controls.termUnitLabel);
  const updateGuestLanguage = $derived(controls.updateGuestLanguage);

  const activationSuccessDialogOpen = $derived(viewState.activationSuccessDialogOpen);
  const activationSuccessUseInstallGuides = $derived(viewState.activationSuccessUseInstallGuides);
  const activeTab = $derived(viewState.activeTab);
  const adminBundleApi = $derived(viewState.adminBundleApi);
  const adminBundleError = $derived(viewState.adminBundleError);
  const appLaunchTarget = $derived(viewState.appLaunchTarget);
  const autoRenewBusy = $derived(viewState.autoRenewBusy);
  const subscriptionReissueDialogOpen = $derived(viewState.subscriptionReissueDialogOpen);
  const subscriptionReissueBusy = $derived(viewState.subscriptionReissueBusy);
  const cfg = $derived(viewState.cfg);
  const languageBusy = $derived(viewState.languageBusy);
  const languageClickGuard = $derived(viewState.languageClickGuard);
  const languageClickGuardArmed = $derived(viewState.languageClickGuardArmed);
  const mode = $derived(viewState.mode);
  const publicInstallSubscription = $derived(viewState.publicInstallSubscription);
  const publicInstallToken = $derived(viewState.publicInstallToken);
  const telegramPlatform = $derived(viewState.telegramPlatform);

  const authState = $derived(authStore);
  const accountView = $derived(shellView.accountView);
  const appDataView = $derived(shellView.appDataView);
  const billingView = $derived(shellView.billingView);
  const languageView = $derived(shellView.languageView);
  const telegramLoginView = $derived(shellView.telegramLoginView);
  const themeView = $derived(shellView.themeView);

  const authStatus = $derived(authState.authStatus);
  const authIsError = $derived(authState.authIsError);
  const authBusy = $derived(authState.authBusy);
  const telegramLoginBusy = $derived(authState.telegramLoginBusy);
  let loginEmailFieldError = $state("");
  let loginEmailTooltipOpen = $state(false);
  const passwordLoginFallback = $derived(authState.passwordLoginFallback);
  const passwordLoginMode = $derived(authState.passwordLoginMode);
  const authResendCooldown = $derived(authState.authResendCooldown);
  const pendingEmail = $derived(authState.pendingEmail);

  const devicesData = $derived(devicesStore.devicesData);
  const devicesLoaded = $derived(devicesStore.devicesLoaded);
  const devicesBusy = $derived(devicesStore.devicesBusy);
  const devicesStatus = $derived(devicesStore.devicesStatus);
  const devicesIsError = $derived(devicesStore.devicesIsError);
  const devicesErrorCode = $derived(devicesStore.devicesErrorCode);

  const supportUnreadCount = $derived(supportStore.unreadCount);
  const supportUnreadLoading = $derived(supportStore.unreadLoading);
  const supportUnreadLoaded = $derived(supportStore.unreadLoaded);
  const linkEmailBusy = $derived(accountStore.linkEmailBusy);
  const linkTelegramBusy = $derived(accountStore.linkTelegramBusy);

  const promoCode = $derived(actionsStore.promoCode);
  const promoBusy = $derived(actionsStore.promoBusy);
  const promoStatus = $derived(actionsStore.promoStatus);
  const promoIsError = $derived(actionsStore.promoIsError);
  const promoFieldError = $derived(actionsStore.promoFieldError);
  const trialBusy = $derived(actionsStore.trialBusy);
  const trialActivationResult = $derived(actionsStore.trialActivationResult);
  const trialActivationError = $derived(actionsStore.trialActivationError);

  $effect(() => {
    loginEmailFieldError = authState.loginEmailFieldError ?? loginEmailFieldError;
    loginEmailTooltipOpen = authState.loginEmailTooltipOpen ?? loginEmailTooltipOpen;
  });

  const emailLinkStatus = $derived(accountView.emailLinkStatus);
  const hasUnlinkedIdentity = $derived(accountView.hasUnlinkedIdentity);
  const privacyPolicyUrl = $derived(accountView.privacyPolicyUrl);
  const profileAvatarUrl = $derived(accountView.profileAvatarUrl);
  const profileEmail = $derived(accountView.profileEmail);
  const profileTelegramId = $derived(accountView.profileTelegramId);
  const serverStatusUrl = $derived(accountView.serverStatusUrl);
  const supportUrl = $derived(accountView.supportUrl);
  const telegramNotificationsNeedPrompt = $derived(accountView.telegramNotificationsNeedPrompt);
  const telegramNotificationsStartLink = $derived(accountView.telegramNotificationsStartLink);
  const telegramNotificationsStatus = $derived(accountView.telegramNotificationsStatus);
  const telegramProfileName = $derived(accountView.telegramProfileName);
  const userAgreementUrl = $derived(accountView.userAgreementUrl);

  const appSettings = $derived(appDataView.appSettings);
  const brand = $derived(appDataView.brand);
  const brandTitle = $derived(appDataView.brandTitle);
  const devicesEnabled = $derived(appDataView.devicesEnabled);
  const subscriptionReissueEnabled = $derived(appDataView.subscriptionReissueEnabled);
  const emailAuthEnabled = $derived(appDataView.emailAuthEnabled);
  const methods = $derived(appDataView.methods);
  const plans = $derived(appDataView.plans);
  const referral = $derived(appDataView.referral);
  const referralBonusDetails = $derived(appDataView.referralBonusDetails);
  const referralOneBonusPerReferee = $derived(appDataView.referralOneBonusPerReferee);
  const referralWelcomeBonusDays = $derived(appDataView.referralWelcomeBonusDays);
  const subscription = $derived(appDataView.subscription);
  const subscriptionPurchaseDescription = $derived(appDataView.subscriptionPurchaseDescription);
  const supportEnabled = $derived(appDataView.supportEnabled);

  const canChangeTariff = $derived(billingView.canChangeTariff);
  const currentTariffName = $derived(billingView.currentTariffName);
  const hasActiveTariffSubscription = $derived(billingView.hasActiveTariffSubscription);
  const hasMultipleTariffs = $derived(billingView.hasMultipleTariffs);
  const premiumTrafficTopupBarClickable = $derived(billingView.premiumTrafficTopupBarClickable);
  const premiumTrafficTopupUnlocked = $derived(billingView.premiumTrafficTopupUnlocked);
  const regularTrafficTopupBarClickable = $derived(billingView.regularTrafficTopupBarClickable);
  const regularTrafficTopupUnlocked = $derived(billingView.regularTrafficTopupUnlocked);
  const selectedTariff = $derived(billingView.selectedTariff);
  const selectedTariffPlans = $derived(billingView.selectedTariffPlans);
  const singleTariffMode = $derived(billingView.singleTariffMode);
  const tariffCatalog = $derived(billingView.tariffCatalog);
  const tariffMode = $derived(billingView.tariffMode);
  const trafficMode = $derived(billingView.trafficMode);

  const currentLang = $derived(shellView.currentLang);
  const isAdmin = $derived(shellView.isAdmin);
  const currentLanguageOption = $derived(languageView.currentLanguageOption ?? null);
  const languageOptions = $derived(languageView.languageOptions);
  const telegramLoginChecking = $derived(telegramLoginView.telegramLoginChecking);
  const telegramLoginLabel = $derived(telegramLoginView.telegramLoginLabel);
  const telegramLoginUnavailable = $derived(telegramLoginView.telegramLoginUnavailable);
  const telegramLoginUnavailableMessage = $derived(
    telegramLoginView.telegramLoginUnavailableMessage
  );
  const telegramMiniAppContext = $derived(shellView.telegramMiniAppContext);
  const shellStyle = $derived(themeView.shellStyle);
  const shellThemeClass = $derived(themeView.shellThemeClass);
  const shellToneClass = $derived(themeView.shellToneClass);
  const user = $derived(shellView.user);
  const userLanguage = $derived(shellView.userLanguage);

  const activateTrial = $derived(appActions.activateTrial);
  const applyPromo = $derived(appActions.applyPromo);
  const backToTariffList = $derived(appActions.backToTariffList);
  const clearPromoFieldError = $derived(appActions.clearPromoFieldError);
  const closeDeviceTopupModal = $derived(appActions.closeDeviceTopupModal);
  const continueWithSelectedTariff = $derived(appActions.continueWithSelectedTariff);
  const copyText = $derived(appActions.copyText);
  const disconnectDevice = $derived(appActions.disconnectDevice);
  const openSubscriptionReissueDialog = $derived(appActions.openSubscriptionReissueDialog);
  const closeSubscriptionReissueDialog = $derived(appActions.closeSubscriptionReissueDialog);
  const confirmSubscriptionReissue = $derived(appActions.confirmSubscriptionReissue);
  const goDevices = $derived(appActions.goDevices);
  const goHome = $derived(appActions.goHome);
  const goInvite = $derived(appActions.goInvite);
  const goSettings = $derived(appActions.goSettings);
  const goSupport = $derived(appActions.goSupport);
  const linkTelegramAndActivateTrial = $derived(appActions.linkTelegramAndActivateTrial);
  const linkTelegramAndClaimReferralWelcome = $derived(
    appActions.linkTelegramAndClaimReferralWelcome
  );
  const loadDevices = $derived(appActions.loadDevices);
  const openAdminPanel = $derived(appActions.openAdminPanel);
  const openAppLaunchTarget = $derived(appActions.openAppLaunchTarget);
  const openAppLink = $derived(appActions.openAppLink);
  const openConnectLink = $derived(appActions.openConnectLink);
  const openDeviceTopupModal = $derived(appActions.openDeviceTopupModal);
  const openExternalLink = $derived(appActions.openExternalLink);
  const openInstallOrConnect = $derived(appActions.openInstallOrConnect);
  const openLoginTelegram = $derived(appActions.openLoginTelegram);
  const openPaymentModal = $derived(appActions.openPaymentModal);
  const openPremiumTopupModal = $derived(appActions.openPremiumTopupModal);
  const openPublicConnectLink = $derived(appActions.openPublicConnectLink);
  const openRegularTopupModal = $derived(appActions.openRegularTopupModal);
  const openSettingsLinkEmailDialog = $derived(appActions.openSettingsLinkEmailDialog);
  const openSettingsSetPasswordDialog = $derived(appActions.openSettingsSetPasswordDialog);
  const openTariffChangeModal = $derived(appActions.openTariffChangeModal);
  const openTelegramNotificationsBot = $derived(appActions.openTelegramNotificationsBot);
  const openTrialInstallOrConnect = $derived(appActions.openTrialInstallOrConnect);
  const primaryPayActionLabel = $derived(appActions.primaryPayActionLabel);
  const refreshAppLaunchTarget = $derived(appActions.refreshAppLaunchTarget);
  const selectTariff = $derived(appActions.selectTariff);
  const setPromoCode = $derived(appActions.setPromoCode);
  const toggleAutoRenew = $derived(appActions.toggleAutoRenew);
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
      bind:email={authStore.email}
      bind:emailPassword={authStore.emailPassword}
      bind:emailCode={authStore.emailCode}
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
      onBackToLogin={() => {
        screen = "login";
      }}
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
      {subscriptionReissueEnabled}
      {subscriptionReissueBusy}
      {openSubscriptionReissueDialog}
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
      {actionsStore}
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
      {subscriptionReissueDialogOpen}
      {subscriptionReissueBusy}
      {confirmSubscriptionReissue}
      {closeSubscriptionReissueDialog}
      openLinkEmailDialog={openSettingsLinkEmailDialog}
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
