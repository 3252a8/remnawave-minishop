<script lang="ts">
  import { getSettingsStore } from "$lib/admin/context";
  import { Input, Textarea } from "$components/ui/index.js";
  import { Save, X } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton } from "$components/patterns/admin/index.js";
  import { Switch } from "$components/ui/primitives.js";
  import {
    DISPOSABLE_EMAIL_DOMAINS_PLACEHOLDER,
    REFERRAL_RULE_KEYS,
    REFERRAL_SETTING_KEYS,
    REFERRAL_WELCOME_KEYS,
    boolValue as resolveBoolValue,
    dirtyCount as resolveDirtyCount,
    inputValueForKey as resolveInputValueForKey,
    isSettingDirty as resolveIsSettingDirty,
    textValueForKey as resolveTextValueForKey,
    valueForKey as resolveValueForKey,
    type SettingsDirtyState,
  } from "$lib/admin/tariffSettings";
  import type { SettingField, SettingsSavedPayload } from "$lib/admin/stores/settingsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    at,
    settingsDirty = {},
    settingsFieldMap = new Map<string, SettingField>(),
    settingsSaving = false,
    onSettingsSaved = () => {},
  }: {
    at: TranslateFn;
    settingsDirty?: SettingsDirtyState;
    settingsFieldMap?: Map<string, SettingField>;
    settingsSaving?: boolean;
    onSettingsSaved?: (payload: SettingsSavedPayload) => void | Promise<void>;
  } = $props();

  const settingsStore = getSettingsStore();

  const referralDirtyCount = $derived(
    REFERRAL_SETTING_KEYS.filter((key) => Boolean(settingsDirty[key])).length
  );

  function valueForKey(
    key: string,
    dirty: SettingsDirtyState = settingsDirty,
    fieldMap = settingsFieldMap
  ): unknown {
    return resolveValueForKey(key, dirty, fieldMap);
  }

  function boolValue(
    key: string,
    dirty: SettingsDirtyState = settingsDirty,
    fieldMap = settingsFieldMap
  ): boolean {
    return resolveBoolValue(key, dirty, fieldMap);
  }

  function inputValueForKey(key: string): string | number {
    return resolveInputValueForKey(key, settingsDirty, settingsFieldMap);
  }

  function textValueForKey(key: string): string {
    return resolveTextValueForKey(key, settingsDirty, settingsFieldMap);
  }

  function isSettingDirty(key: string, dirty: SettingsDirtyState = settingsDirty): boolean {
    return resolveIsSettingDirty(key, dirty);
  }

  function dirtyCount(keys: readonly string[], dirty: SettingsDirtyState = settingsDirty): number {
    return resolveDirtyCount(keys, dirty);
  }

  function setSetting(key: string, value: unknown): void {
    if (!settingsFieldMap.has(key)) return;
    settingsStore.markDirty(key, value);
  }

  function settingInputHandler(key: string): (event: Event) => void {
    return (event: Event) => {
      const input = event.currentTarget as HTMLInputElement | HTMLTextAreaElement | null;
      setSetting(key, input?.value ?? "");
    };
  }

  function resetSetting(key: string): void {
    settingsStore.clearDirty(key);
  }

  async function saveTariffSettings(): Promise<void> {
    await settingsStore.saveSettings(onSettingsSaved);
  }
</script>

<article class="admin-card admin-tariff-settings-card">
  <header class="admin-card-head">
    <div>
      <h3>{at("tariffs_referral_title", {}, "Реферальная программа")}</h3>
      <small>
        {at(
          "tariffs_referral_subtitle",
          {},
          "Настройки приветственного бонуса, правил начисления и защиты от одноразовых email."
        )}
      </small>
    </div>
    <div class="admin-editor-section-actions">
      <AdminBadge
        variant={Number(
          valueForKey("REFERRAL_WELCOME_BONUS_DAYS", settingsDirty, settingsFieldMap) || 0
        ) > 0
          ? "success"
          : "muted"}
      >
        {Number(valueForKey("REFERRAL_WELCOME_BONUS_DAYS", settingsDirty, settingsFieldMap) || 0) >
        0
          ? at("enabled", {}, "Включено")
          : at("disabled", {}, "Выключено")}
      </AdminBadge>
      {#if referralDirtyCount}
        <AdminBadge variant="warning">
          {at(
            "settings_dirty_count",
            { count: referralDirtyCount },
            `Изменений: ${referralDirtyCount}`
          )}
        </AdminBadge>
        <AdminButton
          size="sm"
          variant="primary"
          onclick={saveTariffSettings}
          disabled={settingsSaving}
        >
          <Save size={13} />
          {settingsSaving ? at("btn_saving", {}, "Сохранение...") : at("btn_save", {}, "Сохранить")}
        </AdminButton>
      {/if}
    </div>
  </header>

  <div class="admin-card-body admin-trial-settings-body">
    <div class="admin-settings-field-groups admin-trial-settings-groups">
      <section
        class="admin-settings-field-group"
        class:is-dirty={dirtyCount(REFERRAL_WELCOME_KEYS, settingsDirty)}
      >
        <header class="admin-settings-field-group-head">
          <div class="admin-settings-field-group-head-copy">
            <strong>{at("tariffs_referral_group_welcome", {}, "Приветственный бонус")}</strong>
            <small>
              {at(
                "tariffs_referral_group_welcome_hint",
                {},
                "Дни, которые получает приглашённый пользователь после регистрации по ссылке."
              )}
            </small>
          </div>
          {#if dirtyCount(REFERRAL_WELCOME_KEYS, settingsDirty)}
            <AdminBadge variant="warning">
              {at(
                "settings_dirty_count",
                { count: dirtyCount(REFERRAL_WELCOME_KEYS, settingsDirty) },
                `Изменений: ${dirtyCount(REFERRAL_WELCOME_KEYS, settingsDirty)}`
              )}
            </AdminBadge>
          {/if}
        </header>
        <div class="admin-settings-field-group-body">
          <div
            class="admin-setting admin-trial-setting-row"
            class:is-dirty={isSettingDirty("REFERRAL_WELCOME_BONUS_DAYS", settingsDirty)}
          >
            <div class="admin-setting-meta">
              <strong>
                {at("tariffs_referral_welcome_bonus_days", {}, "Приветственный бонус, дней")}
                {#if isSettingDirty("REFERRAL_WELCOME_BONUS_DAYS", settingsDirty)}
                  <AdminBadge variant="warning"
                    >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                  >
                {/if}
              </strong>
              <code>REFERRAL_WELCOME_BONUS_DAYS</code>
            </div>
            <div class="admin-setting-control">
              <Input
                class="input"
                type="number"
                min="0"
                step="1"
                value={inputValueForKey("REFERRAL_WELCOME_BONUS_DAYS")}
                oninput={settingInputHandler("REFERRAL_WELCOME_BONUS_DAYS")}
              />
              {#if isSettingDirty("REFERRAL_WELCOME_BONUS_DAYS", settingsDirty)}
                <AdminButton
                  size="sm"
                  variant="ghost"
                  onclick={() => resetSetting("REFERRAL_WELCOME_BONUS_DAYS")}
                >
                  <X size={12} />
                  {at("reset", {}, "Сбросить")}
                </AdminButton>
              {/if}
            </div>
          </div>

          <div
            class="admin-setting admin-trial-setting-row"
            class:is-dirty={isSettingDirty(
              "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
              settingsDirty
            )}
          >
            <div class="admin-setting-meta">
              <strong>
                {at(
                  "tariffs_referral_without_telegram",
                  {},
                  "Начислять welcome bonus без Telegram"
                )}
                {#if isSettingDirty("REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED", settingsDirty)}
                  <AdminBadge variant="warning"
                    >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                  >
                {/if}
              </strong>
              <code>REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED</code>
            </div>
            <div class="admin-setting-control">
              <div class="admin-setting-switch">
                <Switch.Root
                  aria-label={at(
                    "tariffs_referral_without_telegram",
                    {},
                    "Начислять welcome bonus без Telegram"
                  )}
                  checked={boolValue(
                    "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
                    settingsDirty,
                    settingsFieldMap
                  )}
                  onCheckedChange={(checked) =>
                    setSetting("REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED", checked)}
                  class="admin-switch-root"
                >
                  <Switch.Thumb class="admin-switch-thumb" />
                </Switch.Root>
                <span
                  >{boolValue(
                    "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
                    settingsDirty,
                    settingsFieldMap
                  )
                    ? at("enabled", {}, "Включено")
                    : at("disabled", {}, "Выключено")}</span
                >
              </div>
              {#if isSettingDirty("REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED", settingsDirty)}
                <AdminButton
                  size="sm"
                  variant="ghost"
                  onclick={() => resetSetting("REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED")}
                >
                  <X size={12} />
                  {at("reset", {}, "Сбросить")}
                </AdminButton>
              {/if}
            </div>
          </div>
        </div>
      </section>

      <section
        class="admin-settings-field-group"
        class:is-dirty={dirtyCount(REFERRAL_RULE_KEYS, settingsDirty)}
      >
        <header class="admin-settings-field-group-head">
          <div class="admin-settings-field-group-head-copy">
            <strong>{at("tariffs_referral_group_rules", {}, "Правила и антиабьюз")}</strong>
            <small>
              {at(
                "tariffs_referral_group_rules_hint",
                {},
                "Ограничения повторных бонусов и домены одноразовой почты для no-Telegram аккаунтов."
              )}
            </small>
          </div>
          {#if dirtyCount(REFERRAL_RULE_KEYS, settingsDirty)}
            <AdminBadge variant="warning">
              {at(
                "settings_dirty_count",
                { count: dirtyCount(REFERRAL_RULE_KEYS, settingsDirty) },
                `Изменений: ${dirtyCount(REFERRAL_RULE_KEYS, settingsDirty)}`
              )}
            </AdminBadge>
          {/if}
        </header>
        <div class="admin-settings-field-group-body">
          <div
            class="admin-setting admin-trial-setting-row"
            class:is-dirty={isSettingDirty("REFERRAL_ONE_BONUS_PER_REFEREE", settingsDirty)}
          >
            <div class="admin-setting-meta">
              <strong>
                {at(
                  "tariffs_referral_one_bonus_per_referee",
                  {},
                  "Бонусы только за первый платёж приглашённого"
                )}
                {#if isSettingDirty("REFERRAL_ONE_BONUS_PER_REFEREE", settingsDirty)}
                  <AdminBadge variant="warning"
                    >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                  >
                {/if}
              </strong>
              <code>REFERRAL_ONE_BONUS_PER_REFEREE</code>
              <small>
                {at(
                  "tariffs_referral_one_bonus_per_referee_hint",
                  {},
                  "Если включено, повторные покупки того же приглашённого пользователя больше не начисляют бонусы ни ему, ни пригласившему. Первый успешный платёж остаётся бонусным."
                )}
              </small>
            </div>
            <div class="admin-setting-control">
              <div class="admin-setting-switch">
                <Switch.Root
                  aria-label={at(
                    "tariffs_referral_one_bonus_per_referee",
                    {},
                    "Бонусы только за первый платёж приглашённого"
                  )}
                  checked={boolValue(
                    "REFERRAL_ONE_BONUS_PER_REFEREE",
                    settingsDirty,
                    settingsFieldMap
                  )}
                  onCheckedChange={(checked) =>
                    setSetting("REFERRAL_ONE_BONUS_PER_REFEREE", checked)}
                  class="admin-switch-root"
                >
                  <Switch.Thumb class="admin-switch-thumb" />
                </Switch.Root>
                <span
                  >{boolValue("REFERRAL_ONE_BONUS_PER_REFEREE", settingsDirty, settingsFieldMap)
                    ? at("enabled", {}, "Включено")
                    : at("disabled", {}, "Выключено")}</span
                >
              </div>
              {#if isSettingDirty("REFERRAL_ONE_BONUS_PER_REFEREE", settingsDirty)}
                <AdminButton
                  size="sm"
                  variant="ghost"
                  onclick={() => resetSetting("REFERRAL_ONE_BONUS_PER_REFEREE")}
                >
                  <X size={12} />
                  {at("reset", {}, "Сбросить")}
                </AdminButton>
              {/if}
            </div>
          </div>

          <div
            class="admin-setting admin-trial-setting-row"
            class:is-dirty={isSettingDirty("DISPOSABLE_EMAIL_DOMAINS", settingsDirty)}
          >
            <div class="admin-setting-meta">
              <strong>
                {at("tariffs_referral_disposable_domains", {}, "Disposable email домены")}
                {#if isSettingDirty("DISPOSABLE_EMAIL_DOMAINS", settingsDirty)}
                  <AdminBadge variant="warning"
                    >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                  >
                {/if}
              </strong>
              <code>DISPOSABLE_EMAIL_DOMAINS</code>
              <small>
                {at(
                  "tariffs_referral_disposable_domains_hint",
                  {},
                  "По одному домену на строку или через запятую. Поддомены тоже считаются совпадением."
                )}
              </small>
            </div>
            <div class="admin-setting-control">
              <Textarea
                class="admin-setting-textarea"
                rows={8}
                placeholder={DISPOSABLE_EMAIL_DOMAINS_PLACEHOLDER}
                value={textValueForKey("DISPOSABLE_EMAIL_DOMAINS")}
                oninput={settingInputHandler("DISPOSABLE_EMAIL_DOMAINS")}
              />
              {#if isSettingDirty("DISPOSABLE_EMAIL_DOMAINS", settingsDirty)}
                <AdminButton
                  size="sm"
                  variant="ghost"
                  onclick={() => resetSetting("DISPOSABLE_EMAIL_DOMAINS")}
                >
                  <X size={12} />
                  {at("reset", {}, "Сбросить")}
                </AdminButton>
              {/if}
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</article>
