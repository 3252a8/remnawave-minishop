<script lang="ts">
  import {
    ArrowRight,
    CheckCircle2,
    FileText,
    Mail,
    Send,
    Server,
    Shield,
    UserRound,
  } from "$components/ui/icons.js";

  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import { AttentionDot } from "$components/ui/index.js";
  import { LanguageSelect } from "$components/patterns/webapp/index.js";
  import TelegramNotificationsBanner from "../TelegramNotificationsBanner.svelte";
  import type {
    LanguageOption,
    OpenLinkAction,
    StringAction,
    Translate,
    UserProfile,
    VoidAction,
  } from "$lib/webapp/types.js";

  type Props = {
    currentLang?: string;
    currentLanguageOption?: LanguageOption | null;
    emailAuthEnabled?: boolean;
    emailLinkStatus?: string;
    isAdmin?: boolean;
    languageBusy?: boolean;
    languageClickGuard?: boolean;
    languageClickGuardArmed?: boolean;
    languageMenuOpen?: boolean;
    languageOptions?: LanguageOption[];
    linkEmailBusy?: boolean;
    linkTelegramBusy?: boolean;
    privacyPolicyUrl?: string;
    profileAvatarUrl?: string;
    profileEmail?: string;
    profileTelegramId?: string;
    serverStatusUrl?: string;
    supportUrl?: string;
    telegramNotificationsNeedPrompt?: boolean;
    telegramNotificationsStartLink?: string;
    telegramNotificationsStatus?: string;
    telegramProfileName?: string;
    user?: UserProfile;
    userAgreementUrl?: string;
    userLanguage?: string;
    showLogout?: boolean;
    linkTelegramAccount?: VoidAction;
    openTelegramNotificationsBot?: VoidAction;
    logout?: VoidAction;
    openAdminPanel?: VoidAction;
    openExternalLink?: OpenLinkAction;
    openLinkEmailDialog?: VoidAction;
    openSetPasswordDialog?: VoidAction;
    setLanguageMenuOpen?: (open: boolean) => void;
    t?: Translate;
    updateAccountLanguage?: StringAction;
  };

  let {
    currentLang = "ru",
    currentLanguageOption = null,
    emailAuthEnabled = true,
    emailLinkStatus = "",
    isAdmin = false,
    languageBusy = false,
    languageClickGuard = false,
    languageClickGuardArmed = false,
    languageMenuOpen = $bindable(false),
    languageOptions = [],
    linkEmailBusy = false,
    linkTelegramBusy = false,
    privacyPolicyUrl = "",
    profileAvatarUrl = "",
    profileEmail = "",
    profileTelegramId = "",
    serverStatusUrl = "",
    supportUrl = "",
    telegramNotificationsNeedPrompt = false,
    telegramNotificationsStartLink = "",
    telegramNotificationsStatus = "unknown",
    telegramProfileName = "",
    user = {},
    userAgreementUrl = "",
    userLanguage = "",
    showLogout = true,
    linkTelegramAccount = () => {},
    openTelegramNotificationsBot = () => {},
    logout = () => {},
    openAdminPanel = () => {},
    openExternalLink = () => {},
    openLinkEmailDialog = () => {},
    openSetPasswordDialog = () => {},
    setLanguageMenuOpen = () => {},
    t = (key) => key,
    updateAccountLanguage = () => {},
  }: Props = $props();

  const showEmailAccount = $derived(emailAuthEnabled || Boolean(user?.email));
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
          <strong>{t("wa_settings_admin_panel", {}, "Админ-панель")}</strong>
          <small>{t("wa_settings_admin_panel_hint", {}, "Управление приложением")}</small>
        </span>
        <ArrowRight size={17} />
      </button>
    </div>
  {/if}
  <div class="settings-links-block">
    <div class="settings-divider" aria-hidden="true"></div>
    {#if user?.telegram_linked}
      <div class="settings-row settings-row-linked">
        <CheckCircle2 size={21} />
        <span>
          <strong>{t("wa_settings_telegram_linked_title")}</strong>
          <small>{profileTelegramId}</small>
        </span>
      </div>
    {:else}
      <Button
        variant="telegram"
        class="wide settings-telegram-link-btn attention-wrap"
        onclick={linkTelegramAccount}
        disabled={linkTelegramBusy}
      >
        <AttentionDot />
        <Send size={18} />
        {t("wa_settings_link_telegram_action")}
      </Button>
    {/if}
    {#if user?.email}
      <div class="settings-row settings-row-linked settings-row-linked-with-action">
        <CheckCircle2 size={21} />
        <span>
          <strong>{t("wa_settings_email_linked_title")}</strong>
          <small>{user?.email}</small>
        </span>
        {#if emailAuthEnabled && user?.email_verified}
          <Button
            data-webapp-action="open-set-password"
            variant="secondary"
            size="sm"
            class="settings-inline-action"
            onclick={openSetPasswordDialog}
          >
            {user?.password_auth_enabled
              ? t("wa_settings_change_password_action")
              : t("wa_settings_set_password_action")}
          </Button>
        {/if}
      </div>
    {:else if emailAuthEnabled}
      <button
        data-webapp-action="open-link-email"
        class="settings-row attention-wrap"
        type="button"
        onclick={openLinkEmailDialog}
        disabled={linkEmailBusy}
      >
        <AttentionDot />
        <Mail size={21} />
        <span>
          <strong>{t("wa_settings_link_email_action")}</strong>
          <small>{emailLinkStatus}</small>
        </span>
        <ArrowRight size={17} />
      </button>
    {/if}
    <div class="settings-divider" aria-hidden="true"></div>
  </div>
  <div class="settings-list" class:settings-list--language-open={languageMenuOpen}>
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
    {#if serverStatusUrl}
      <button
        class="settings-row settings-row-status"
        type="button"
        onclick={() => openExternalLink(serverStatusUrl)}
      >
        <Server size={21} />
        <span><strong>{t("menu_server_status_button")}</strong></span>
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
</main>
