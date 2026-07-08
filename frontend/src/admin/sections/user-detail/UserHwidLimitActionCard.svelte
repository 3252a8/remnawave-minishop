<script lang="ts">
  import { getUsersStore } from "$lib/admin/context";
  import { AdminBadge, AdminButton, AdminSectionHeader } from "$components/patterns/admin/index.js";
  import { Checkbox, Input } from "$components/ui/index.js";
  import { Label } from "$components/ui/primitives.js";
  import type { ActiveSubscription, TranslateFn } from "./userDetailTypes";

  let {
    at,
    activeSubscription,
    userActionBusy = false,
    hwidLimitDirty = false,
    hwidLimitDraftValid = false,
    hwidUnlimitedDraft = false,
    hwidLimitLabel,
  }: {
    at: TranslateFn;
    activeSubscription: ActiveSubscription;
    userActionBusy?: boolean;
    hwidLimitDirty?: boolean;
    hwidLimitDraftValid?: boolean;
    hwidUnlimitedDraft?: boolean;
    hwidLimitLabel: (sub: Record<string, unknown> | null | undefined) => string;
  } = $props();

  const usersStore = getUsersStore();
</script>

<section
  class="admin-user-action-sheet admin-user-action-sheet--hwid-limit"
  class:is-dirty={hwidLimitDirty}
>
  <AdminSectionHeader
    title={at("user_hwid_limit_card_title", {}, "HWID-устройства")}
    description={at(
      "user_hwid_limit_card_hint",
      {},
      "Ручной лимит устройств для пользователя. Пустое поле вернёт тарифный или default-лимит."
    )}
  />
  <div class="admin-user-action-sheet-body admin-user-override-stack">
    <Label.Root class="admin-field-label admin-extend-field">
      <span>{at("user_hwid_limit_input", {}, "Лимит устройств")}</span>
      <small
        >{at(
          "user_hwid_limit_input_hint",
          {},
          "Пусто — тариф/default; 0 или галочка — безлимит."
        )}</small
      >
      <Input
        class="input"
        type="number"
        min="0"
        step="1"
        placeholder={at("user_hwid_limit_default_placeholder", {}, "Тариф")}
        disabled={hwidUnlimitedDraft}
        aria-label={at("user_hwid_limit_input", {}, "Лимит устройств")}
        bind:value={usersStore.hwidDeviceLimitDraft}
      />
    </Label.Root>
  </div>
  <div class="admin-user-action-sheet-footer admin-override-card-footer">
    <div class="admin-override-card-toolbar">
      <label class="admin-override-unlimited-label">
        <Checkbox
          bind:checked={usersStore.hwidUnlimitedDraft}
          aria-label={at("user_override_unlimited_short", {}, "Безлимит")}
        />
        <span>{at("user_override_unlimited_short", {}, "Безлимит")}</span>
      </label>
      <div class="admin-action-save-controls">
        {#if hwidLimitDirty}
          <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge>
        {/if}
        <AdminButton
          variant="primary"
          onclick={usersStore.saveHwidDeviceLimit}
          disabled={userActionBusy || !hwidLimitDirty || !hwidLimitDraftValid}
        >
          {at("user_hwid_limit_save", {}, "Сохранить")}
        </AdminButton>
      </div>
    </div>
    <div class="admin-override-status-lines">
      {#if hwidLimitDirty}
        <span class="admin-unsaved-hint">
          {at("user_action_unsaved_hint", {}, "Есть несохранённые изменения")}
        </span>
      {/if}
      {#if !hwidLimitDraftValid}
        <span class="admin-invalid-hint">
          {at(
            "hwid_limit_invalid",
            {},
            "Введите целое число устройств от 0 до 1 000 000 или включите безлимит"
          )}
        </span>
      {/if}
      <span class="admin-meta-truncate">
        {at(
          "user_hwid_limit_status",
          { current: hwidLimitLabel(activeSubscription) },
          `Сейчас: ${hwidLimitLabel(activeSubscription)}`
        )}
      </span>
    </div>
  </div>
</section>
