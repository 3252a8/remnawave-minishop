<script lang="ts">
  import type { Readable, Writable } from "svelte/store";

  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import type { AppActionRuntime } from "../lib/webapp/appActionRuntime.js";
  import type { AppShellView } from "../lib/webapp/appShellView.js";
  import type { LanguageOption } from "../lib/webapp/languageView.js";
  import type { DevicesStore } from "../lib/webapp/stores/devicesStore.js";
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

  type Props = {
    accountStore: WritableStoreLike;
    shellView?: AppShellView | null;
    appActions?: AppActionRuntime | null;
    actionsStore: ReadableStoreLike;
    activateTrial?: Action;
    activationSuccessDialogOpen?: boolean;
    activationSuccessUseInstallGuides?: boolean;
    activeTab?: string;
    adminBundleApi?: AnyRecord | null;
    adminBundleError?: string;
    adminMountTarget?: HTMLElement | null;
    appLaunchTarget?: string;
    appSettings?: AnyRecord;
    applyPromo?: Action;
    authBusy?: boolean;
    authIsError?: boolean;
    authResendCooldown?: number;
    authStatus?: string;
    authStore: WritableStoreLike;
    autoRenewBusy?: boolean;
    backToTariffList?: Action;
    billingStore: WritableStoreLike;
    brand?: AnyRecord;
    brandTitle?: string;
    canChangeTariff?: boolean;
    cfg?: AnyRecord;
    clearPromoFieldError?: Action;
    closeActivationSuccessDialog?: Action;
    closeDeviceTopupModal?: Action;
    continueWithSelectedTariff?: Action;
    copyText?: Action;
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
    disconnectDevice?: Action;
    emailAuthEnabled?: boolean;
    emailLinkStatus?: string;
    goDevices?: Action;
    goHome?: Action;
    goInvite?: Action;
    goSettings?: Action;
    goSupport?: Action;
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
    linkTelegramAndActivateTrial?: Action;
    linkTelegramAndClaimReferralWelcome?: Action;
    linkTelegramBusy?: boolean;
    loadDevices?: Action;
    loginEmailFieldError?: string;
    loginEmailTooltipOpen?: boolean;
    methods?: AnyRecord[];
    mode?: string;
    openAdminPanel?: Action;
    openAppLaunchTarget?: Action;
    openAppLink?: Action;
    openConnectLink?: Action;
    openDeviceTopupModal?: Action;
    openExternalLink?: Action;
    openInstallOrConnect?: Action;
    openLoginTelegram?: Action;
    openPaymentModal?: Action;
    openPremiumTopupModal?: Action;
    openPublicConnectLink?: Action;
    openRegularTopupModal?: Action;
    openSettingsLinkEmailDialog?: Action;
    openSettingsSetPasswordDialog?: Action;
    openTariffChangeModal?: Action;
    openTelegramNotificationsBot?: Action;
    openTrialInstallOrConnect?: Action;
    passwordLoginFallback?: boolean;
    passwordLoginMode?: boolean;
    pendingEmail?: string;
    plans?: AnyRecord[];
    premiumTrafficTopupBarClickable?: boolean;
    premiumTrafficTopupUnlocked?: boolean;
    primaryPayActionLabel?: () => string;
    privacyPolicyUrl?: string;
    profileAvatarUrl?: string;
    profileEmail?: string;
    profileTelegramId?: string;
    promoBusy?: boolean;
    promoCode?: string;
    promoFieldError?: string;
    promoIsError?: boolean;
    promoStatus?: string;
    publicInstallSubscription?: AnyRecord | null;
    publicInstallToken?: string;
    referral?: AnyRecord;
    referralBonusDetails?: AnyRecord[];
    referralOneBonusPerReferee?: boolean;
    referralWelcomeBonusDays?: number;
    refreshAppLaunchTarget?: Action;
    regularTrafficTopupBarClickable?: boolean;
    regularTrafficTopupUnlocked?: boolean;
    screen?: string;
    selectedTariff?: AnyRecord | null;
    selectedTariffPlans?: AnyRecord[];
    selectTariff?: Action;
    serverStatusUrl?: string;
    setLanguageMenuOpen: (open: boolean) => void;
    setPasswordLoginMode: (enabled: boolean) => void;
    setPromoCode?: (value: string) => void;
    shellStyle?: string;
    shellThemeClass?: string;
    shellToneClass?: string;
    singleTariffMode?: boolean;
    submitEmailOnEnter?: Action;
    subscription?: AnyRecord;
    subscriptionPurchaseDescription?: string;
    supportEnabled?: boolean;
    supportStore: ReadableStoreLike;
    supportUnreadCount?: number;
    supportUnreadLoaded?: boolean;
    supportUnreadLoading?: boolean;
    supportUrl?: string;
    t: Translate;
    tariffCatalog?: AnyRecord[];
    tariffMode?: boolean;
    telegramLoginBusy?: boolean;
    telegramLoginChecking?: boolean;
    telegramLoginLabel?: string;
    telegramLoginUnavailable?: boolean;
    telegramLoginUnavailableMessage?: string;
    telegramMiniAppContext?: boolean;
    telegramNotificationsNeedPrompt?: boolean;
    telegramNotificationsStartLink?: string;
    telegramNotificationsStatus?: string;
    telegramPlatform?: string;
    telegramProfileName?: string;
    termUnitLabel?: Action;
    toggleAutoRenew?: Action;
    trafficMode?: boolean;
    trialActivationError?: string;
    trialActivationResult?: AnyRecord | null;
    trialBusy?: boolean;
    user?: AnyRecord;
    userAgreementUrl?: string;
    userLanguage?: string;
    updateGuestLanguage: (language: string) => void;
  };

  let {
    accountStore,
    shellView = null,
    appActions = null,
    actionsStore,
    activateTrial: activateTrialProp = noopAction,
    activationSuccessDialogOpen = false,
    activationSuccessUseInstallGuides = false,
    activeTab = "home",
    adminBundleApi = null,
    adminBundleError = "",
    adminMountTarget = $bindable(null),
    appLaunchTarget = "",
    appSettings: appSettingsProp = {},
    applyPromo: applyPromoProp = noopAction,
    authStore,
    autoRenewBusy = false,
    backToTariffList: backToTariffListProp = noopAction,
    billingStore,
    brand: brandProp = {},
    brandTitle: brandTitleProp = "",
    canChangeTariff: canChangeTariffProp = false,
    cfg = {},
    clearPromoFieldError: clearPromoFieldErrorProp = noopAction,
    closeActivationSuccessDialog = noopAction,
    closeDeviceTopupModal: closeDeviceTopupModalProp = noopAction,
    continueWithSelectedTariff: continueWithSelectedTariffProp = noopAction,
    copyText: copyTextProp = noopAction,
    currentLang: currentLangProp = "ru",
    currentLanguageOption: currentLanguageOptionProp = null,
    currentTariffName: currentTariffNameProp = "",
    devicesEnabled: devicesEnabledProp = false,
    devicesStore,
    disconnectDevice: disconnectDeviceProp = noopAction,
    emailAuthEnabled: emailAuthEnabledProp = true,
    emailLinkStatus: emailLinkStatusProp = "",
    goDevices: goDevicesProp = noopAction,
    goHome: goHomeProp = noopAction,
    goInvite: goInviteProp = noopAction,
    goSettings: goSettingsProp = noopAction,
    goSupport: goSupportProp = noopAction,
    hasActiveTariffSubscription: hasActiveTariffSubscriptionProp = false,
    hasMultipleTariffs: hasMultipleTariffsProp = false,
    hasUnlinkedIdentity: hasUnlinkedIdentityProp = false,
    isAdmin: isAdminProp = false,
    languageBusy = false,
    languageClickGuard = false,
    languageClickGuardArmed = false,
    languageMenuOpen = $bindable(false),
    languageOptions: languageOptionsProp = [],
    linkTelegramAndActivateTrial: linkTelegramAndActivateTrialProp = noopAction,
    linkTelegramAndClaimReferralWelcome: linkTelegramAndClaimReferralWelcomeProp = noopAction,
    loadDevices: loadDevicesProp = noopAction,
    loginEmailFieldError: loginEmailFieldErrorProp = "",
    loginEmailTooltipOpen: loginEmailTooltipOpenProp = false,
    methods: methodsProp = [],
    mode = "loading",
    openAdminPanel: openAdminPanelProp = noopAction,
    openAppLaunchTarget: openAppLaunchTargetProp = noopAction,
    openAppLink: openAppLinkProp = noopAction,
    openConnectLink: openConnectLinkProp = noopAction,
    openDeviceTopupModal: openDeviceTopupModalProp = noopAction,
    openExternalLink: openExternalLinkProp = noopAction,
    openInstallOrConnect: openInstallOrConnectProp = noopAction,
    openLoginTelegram: openLoginTelegramProp = noopAction,
    openPaymentModal: openPaymentModalProp = noopAction,
    openPremiumTopupModal: openPremiumTopupModalProp = noopAction,
    openPublicConnectLink: openPublicConnectLinkProp = noopAction,
    openRegularTopupModal: openRegularTopupModalProp = noopAction,
    openSettingsLinkEmailDialog: openSettingsLinkEmailDialogProp = noopAction,
    openSettingsSetPasswordDialog: openSettingsSetPasswordDialogProp = noopAction,
    openTariffChangeModal: openTariffChangeModalProp = noopAction,
    openTelegramNotificationsBot: openTelegramNotificationsBotProp = noopAction,
    openTrialInstallOrConnect: openTrialInstallOrConnectProp = noopAction,
    plans: plansProp = [],
    premiumTrafficTopupBarClickable: premiumTrafficTopupBarClickableProp = false,
    premiumTrafficTopupUnlocked: premiumTrafficTopupUnlockedProp = false,
    primaryPayActionLabel: primaryPayActionLabelProp = noopPrimaryPayActionLabel,
    privacyPolicyUrl: privacyPolicyUrlProp = "",
    profileAvatarUrl: profileAvatarUrlProp = "",
    profileEmail: profileEmailProp = "",
    profileTelegramId: profileTelegramIdProp = "",
    publicInstallSubscription = null,
    publicInstallToken = "",
    referral: referralProp = {},
    referralBonusDetails: referralBonusDetailsProp = [],
    referralOneBonusPerReferee: referralOneBonusPerRefereeProp = false,
    referralWelcomeBonusDays: referralWelcomeBonusDaysProp = 0,
    refreshAppLaunchTarget: refreshAppLaunchTargetProp = noopAction,
    regularTrafficTopupBarClickable: regularTrafficTopupBarClickableProp = false,
    regularTrafficTopupUnlocked: regularTrafficTopupUnlockedProp = false,
    screen = $bindable("home"),
    selectedTariff: selectedTariffProp = null,
    selectedTariffPlans: selectedTariffPlansProp = [],
    selectTariff: selectTariffProp = noopAction,
    serverStatusUrl: serverStatusUrlProp = "",
    setLanguageMenuOpen,
    setPasswordLoginMode,
    setPromoCode: setPromoCodeProp = noopAction,
    shellStyle: shellStyleProp = "",
    shellThemeClass: shellThemeClassProp = "",
    shellToneClass: shellToneClassProp = "",
    singleTariffMode: singleTariffModeProp = false,
    submitEmailOnEnter = noopAction,
    subscription: subscriptionProp = {},
    subscriptionPurchaseDescription: subscriptionPurchaseDescriptionProp = "",
    supportEnabled: supportEnabledProp = false,
    supportStore,
    supportUrl: supportUrlProp = "",
    t,
    tariffCatalog: tariffCatalogProp = [],
    tariffMode: tariffModeProp = false,
    telegramLoginChecking: telegramLoginCheckingProp = false,
    telegramLoginLabel: telegramLoginLabelProp = "",
    telegramLoginUnavailable: telegramLoginUnavailableProp = false,
    telegramLoginUnavailableMessage: telegramLoginUnavailableMessageProp = "",
    telegramMiniAppContext: telegramMiniAppContextProp = false,
    telegramNotificationsNeedPrompt: telegramNotificationsNeedPromptProp = false,
    telegramNotificationsStartLink: telegramNotificationsStartLinkProp = "",
    telegramNotificationsStatus: telegramNotificationsStatusProp = "unknown",
    telegramPlatform = "",
    telegramProfileName: telegramProfileNameProp = "",
    termUnitLabel = noopAction,
    toggleAutoRenew: toggleAutoRenewProp = noopAction,
    trafficMode: trafficModeProp = false,
    user: userProp = {},
    userAgreementUrl: userAgreementUrlProp = "",
    userLanguage: userLanguageProp = "",
    updateGuestLanguage,
  }: Props = $props();

  const authState = $derived($authStore);
  const supportState = $derived($supportStore);
  const accountState = $derived($accountStore);
  const actionsState = $derived($actionsStore);
  const accountView = $derived(shellView?.accountView);
  const appDataView = $derived(shellView?.appDataView);
  const billingView = $derived(shellView?.billingView);
  const languageView = $derived(shellView?.languageView);
  const telegramLoginView = $derived(shellView?.telegramLoginView);
  const themeView = $derived(shellView?.themeView);

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

  const supportUnreadCount = $derived(supportState.unreadCount);
  const supportUnreadLoading = $derived(supportState.unreadLoading);
  const supportUnreadLoaded = $derived(supportState.unreadLoaded);
  const linkEmailBusy = $derived(accountState.linkEmailBusy);
  const linkTelegramBusy = $derived(accountState.linkTelegramBusy);

  const promoCode = $derived(actionsState.promoCode);
  const promoBusy = $derived(actionsState.promoBusy);
  const promoStatus = $derived(actionsState.promoStatus);
  const promoIsError = $derived(actionsState.promoIsError);
  const promoFieldError = $derived(actionsState.promoFieldError);
  const trialBusy = $derived(actionsState.trialBusy);
  const trialActivationResult = $derived(actionsState.trialActivationResult);
  const trialActivationError = $derived(actionsState.trialActivationError);

  $effect(() => {
    loginEmailFieldError = authState.loginEmailFieldError ?? loginEmailFieldErrorProp;
    loginEmailTooltipOpen = authState.loginEmailTooltipOpen ?? loginEmailTooltipOpenProp;
  });

  const emailLinkStatus = $derived(shellView ? accountView?.emailLinkStatus : emailLinkStatusProp);
  const hasUnlinkedIdentity = $derived(
    shellView ? accountView?.hasUnlinkedIdentity : hasUnlinkedIdentityProp
  );
  const privacyPolicyUrl = $derived(
    shellView ? accountView?.privacyPolicyUrl : privacyPolicyUrlProp
  );
  const profileAvatarUrl = $derived(
    shellView ? accountView?.profileAvatarUrl : profileAvatarUrlProp
  );
  const profileEmail = $derived(shellView ? accountView?.profileEmail : profileEmailProp);
  const profileTelegramId = $derived(
    shellView ? accountView?.profileTelegramId : profileTelegramIdProp
  );
  const serverStatusUrl = $derived(shellView ? accountView?.serverStatusUrl : serverStatusUrlProp);
  const supportUrl = $derived(shellView ? accountView?.supportUrl : supportUrlProp);
  const telegramNotificationsNeedPrompt = $derived(
    shellView ? accountView?.telegramNotificationsNeedPrompt : telegramNotificationsNeedPromptProp
  );
  const telegramNotificationsStartLink = $derived(
    shellView ? accountView?.telegramNotificationsStartLink : telegramNotificationsStartLinkProp
  );
  const telegramNotificationsStatus = $derived(
    shellView ? accountView?.telegramNotificationsStatus : telegramNotificationsStatusProp
  );
  const telegramProfileName = $derived(
    shellView ? accountView?.telegramProfileName : telegramProfileNameProp
  );
  const userAgreementUrl = $derived(
    shellView ? accountView?.userAgreementUrl : userAgreementUrlProp
  );

  const appSettings = $derived(shellView ? appDataView?.appSettings : appSettingsProp);
  const brand = $derived(shellView ? appDataView?.brand : brandProp);
  const brandTitle = $derived(shellView ? appDataView?.brandTitle : brandTitleProp);
  const devicesEnabled = $derived(shellView ? appDataView?.devicesEnabled : devicesEnabledProp);
  const emailAuthEnabled = $derived(
    shellView ? appDataView?.emailAuthEnabled : emailAuthEnabledProp
  );
  const methods = $derived(shellView ? appDataView?.methods : methodsProp);
  const plans = $derived(shellView ? appDataView?.plans : plansProp);
  const referral = $derived(shellView ? appDataView?.referral : referralProp);
  const referralBonusDetails = $derived(
    shellView ? appDataView?.referralBonusDetails : referralBonusDetailsProp
  );
  const referralOneBonusPerReferee = $derived(
    shellView ? appDataView?.referralOneBonusPerReferee : referralOneBonusPerRefereeProp
  );
  const referralWelcomeBonusDays = $derived(
    shellView ? appDataView?.referralWelcomeBonusDays : referralWelcomeBonusDaysProp
  );
  const subscription = $derived(shellView ? appDataView?.subscription : subscriptionProp);
  const subscriptionPurchaseDescription = $derived(
    shellView ? appDataView?.subscriptionPurchaseDescription : subscriptionPurchaseDescriptionProp
  );
  const supportEnabled = $derived(shellView ? appDataView?.supportEnabled : supportEnabledProp);

  const canChangeTariff = $derived(shellView ? billingView?.canChangeTariff : canChangeTariffProp);
  const currentTariffName = $derived(
    shellView ? billingView?.currentTariffName : currentTariffNameProp
  );
  const hasActiveTariffSubscription = $derived(
    shellView ? billingView?.hasActiveTariffSubscription : hasActiveTariffSubscriptionProp
  );
  const hasMultipleTariffs = $derived(
    shellView ? billingView?.hasMultipleTariffs : hasMultipleTariffsProp
  );
  const premiumTrafficTopupBarClickable = $derived(
    shellView ? billingView?.premiumTrafficTopupBarClickable : premiumTrafficTopupBarClickableProp
  );
  const premiumTrafficTopupUnlocked = $derived(
    shellView ? billingView?.premiumTrafficTopupUnlocked : premiumTrafficTopupUnlockedProp
  );
  const regularTrafficTopupBarClickable = $derived(
    shellView ? billingView?.regularTrafficTopupBarClickable : regularTrafficTopupBarClickableProp
  );
  const regularTrafficTopupUnlocked = $derived(
    shellView ? billingView?.regularTrafficTopupUnlocked : regularTrafficTopupUnlockedProp
  );
  const selectedTariff = $derived(shellView ? billingView?.selectedTariff : selectedTariffProp);
  const selectedTariffPlans = $derived(
    shellView ? billingView?.selectedTariffPlans : selectedTariffPlansProp
  );
  const singleTariffMode = $derived(
    shellView ? billingView?.singleTariffMode : singleTariffModeProp
  );
  const tariffCatalog = $derived(shellView ? billingView?.tariffCatalog : tariffCatalogProp);
  const tariffMode = $derived(shellView ? billingView?.tariffMode : tariffModeProp);
  const trafficMode = $derived(shellView ? billingView?.trafficMode : trafficModeProp);

  const currentLang = $derived(shellView ? shellView.currentLang : currentLangProp);
  const isAdmin = $derived(shellView ? shellView.isAdmin : isAdminProp);
  const currentLanguageOption = $derived(
    shellView ? (languageView?.currentLanguageOption ?? null) : currentLanguageOptionProp
  );
  const languageOptions = $derived(shellView ? languageView?.languageOptions : languageOptionsProp);
  const telegramLoginChecking = $derived(
    shellView ? telegramLoginView?.telegramLoginChecking : telegramLoginCheckingProp
  );
  const telegramLoginLabel = $derived(
    shellView ? telegramLoginView?.telegramLoginLabel : telegramLoginLabelProp
  );
  const telegramLoginUnavailable = $derived(
    shellView ? telegramLoginView?.telegramLoginUnavailable : telegramLoginUnavailableProp
  );
  const telegramLoginUnavailableMessage = $derived(
    shellView
      ? telegramLoginView?.telegramLoginUnavailableMessage
      : telegramLoginUnavailableMessageProp
  );
  const telegramMiniAppContext = $derived(
    shellView ? shellView.telegramMiniAppContext : telegramMiniAppContextProp
  );
  const shellStyle = $derived(shellView ? themeView?.shellStyle : shellStyleProp);
  const shellThemeClass = $derived(shellView ? themeView?.shellThemeClass : shellThemeClassProp);
  const shellToneClass = $derived(shellView ? themeView?.shellToneClass : shellToneClassProp);
  const user = $derived(shellView ? shellView.user : userProp);
  const userLanguage = $derived(shellView ? shellView.userLanguage : userLanguageProp);

  const activateTrial = $derived(appActions ? appActions.activateTrial : activateTrialProp);
  const applyPromo = $derived(appActions ? appActions.applyPromo : applyPromoProp);
  const backToTariffList = $derived(
    appActions ? appActions.backToTariffList : backToTariffListProp
  );
  const clearPromoFieldError = $derived(
    appActions ? appActions.clearPromoFieldError : clearPromoFieldErrorProp
  );
  const closeDeviceTopupModal = $derived(
    appActions ? appActions.closeDeviceTopupModal : closeDeviceTopupModalProp
  );
  const continueWithSelectedTariff = $derived(
    appActions ? appActions.continueWithSelectedTariff : continueWithSelectedTariffProp
  );
  const copyText = $derived(appActions ? appActions.copyText : copyTextProp);
  const disconnectDevice = $derived(
    appActions ? appActions.disconnectDevice : disconnectDeviceProp
  );
  const goDevices = $derived(appActions ? appActions.goDevices : goDevicesProp);
  const goHome = $derived(appActions ? appActions.goHome : goHomeProp);
  const goInvite = $derived(appActions ? appActions.goInvite : goInviteProp);
  const goSettings = $derived(appActions ? appActions.goSettings : goSettingsProp);
  const goSupport = $derived(appActions ? appActions.goSupport : goSupportProp);
  const linkTelegramAndActivateTrial = $derived(
    appActions ? appActions.linkTelegramAndActivateTrial : linkTelegramAndActivateTrialProp
  );
  const linkTelegramAndClaimReferralWelcome = $derived(
    appActions
      ? appActions.linkTelegramAndClaimReferralWelcome
      : linkTelegramAndClaimReferralWelcomeProp
  );
  const loadDevices = $derived(appActions ? appActions.loadDevices : loadDevicesProp);
  const openAdminPanel = $derived(appActions ? appActions.openAdminPanel : openAdminPanelProp);
  const openAppLaunchTarget = $derived(
    appActions ? appActions.openAppLaunchTarget : openAppLaunchTargetProp
  );
  const openAppLink = $derived(appActions ? appActions.openAppLink : openAppLinkProp);
  const openConnectLink = $derived(appActions ? appActions.openConnectLink : openConnectLinkProp);
  const openDeviceTopupModal = $derived(
    appActions ? appActions.openDeviceTopupModal : openDeviceTopupModalProp
  );
  const openExternalLink = $derived(
    appActions ? appActions.openExternalLink : openExternalLinkProp
  );
  const openInstallOrConnect = $derived(
    appActions ? appActions.openInstallOrConnect : openInstallOrConnectProp
  );
  const openLoginTelegram = $derived(
    appActions ? appActions.openLoginTelegram : openLoginTelegramProp
  );
  const openPaymentModal = $derived(
    appActions ? appActions.openPaymentModal : openPaymentModalProp
  );
  const openPremiumTopupModal = $derived(
    appActions ? appActions.openPremiumTopupModal : openPremiumTopupModalProp
  );
  const openPublicConnectLink = $derived(
    appActions ? appActions.openPublicConnectLink : openPublicConnectLinkProp
  );
  const openRegularTopupModal = $derived(
    appActions ? appActions.openRegularTopupModal : openRegularTopupModalProp
  );
  const openSettingsLinkEmailDialog = $derived(
    appActions ? appActions.openSettingsLinkEmailDialog : openSettingsLinkEmailDialogProp
  );
  const openSettingsSetPasswordDialog = $derived(
    appActions ? appActions.openSettingsSetPasswordDialog : openSettingsSetPasswordDialogProp
  );
  const openTariffChangeModal = $derived(
    appActions ? appActions.openTariffChangeModal : openTariffChangeModalProp
  );
  const openTelegramNotificationsBot = $derived(
    appActions ? appActions.openTelegramNotificationsBot : openTelegramNotificationsBotProp
  );
  const openTrialInstallOrConnect = $derived(
    appActions ? appActions.openTrialInstallOrConnect : openTrialInstallOrConnectProp
  );
  const primaryPayActionLabel = $derived(
    appActions ? appActions.primaryPayActionLabel : primaryPayActionLabelProp
  );
  const refreshAppLaunchTarget = $derived(
    appActions ? appActions.refreshAppLaunchTarget : refreshAppLaunchTargetProp
  );
  const selectTariff = $derived(appActions ? appActions.selectTariff : selectTariffProp);
  const setPromoCode = $derived(appActions ? appActions.setPromoCode : setPromoCodeProp);
  const toggleAutoRenew = $derived(appActions ? appActions.toggleAutoRenew : toggleAutoRenewProp);
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
