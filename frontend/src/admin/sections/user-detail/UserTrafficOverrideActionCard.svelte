<script lang="ts">
  import { getUsersStore } from "$lib/admin/context";
  import { AdminBadge, AdminButton, AdminSectionHeader } from "$components/patterns/admin/index.js";
  import { Checkbox, Input } from "$components/ui/index.js";
  import { Label } from "$components/ui/primitives.js";
  import type { ActiveSubscription, TranslateFn } from "./userDetailTypes";

  type TrafficOverrideKind = "premium" | "regular";

  let {
    at,
    kind,
    activeSubscription,
    userActionBusy = false,
    dirty = false,
    draftValid = false,
    unlimitedDraft = false,
  }: {
    at: TranslateFn;
    kind: TrafficOverrideKind;
    activeSubscription: ActiveSubscription;
    userActionBusy?: boolean;
    dirty?: boolean;
    draftValid?: boolean;
    unlimitedDraft?: boolean;
  } = $props();

  const usersStore = getUsersStore();
  const isPremium = $derived(kind === "premium");
  const bonusDraft = $derived(
    isPremium ? usersStore.premiumBonusGbDraft : usersStore.regularBonusGbDraft
  );
  const unlimitedOverride = $derived(
    Boolean(
      isPremium
        ? activeSubscription.premium_unlimited_override
        : activeSubscription.regular_unlimited_override
    )
  );
  const bonusBytes = $derived(
    Number(
      (isPremium
        ? activeSubscription.premium_bonus_bytes
        : activeSubscription.regular_bonus_bytes) || 0
    )
  );
  const bonusGb = $derived(+(bonusBytes / 1024 ** 3).toFixed(2));
  const sheetClass = $derived(`admin-user-action-sheet admin-user-action-sheet--${kind}-override`);

  function setUnlimited(checked: boolean) {
    if (isPremium) {
      usersStore.updateState({ premiumUnlimitedDraft: checked });
      return;
    }
    usersStore.updateState({ regularUnlimitedDraft: checked });
  }

  function setBonus(value: string) {
    if (isPremium) {
      usersStore.updateState({ premiumBonusGbDraft: value });
      return;
    }
    usersStore.updateState({ regularBonusGbDraft: value });
  }

  function saveOverride() {
    if (isPremium) {
      usersStore.savePremiumTrafficOverride();
      return;
    }
    usersStore.saveRegularTrafficOverride();
  }
</script>

<section class={sheetClass} class:is-dirty={dirty}>
  <AdminSectionHeader
    title={isPremium
      ? at("user_premium_override_card_title", {}, "Премиум-трафик")
      : at("user_regular_override_card_title", {}, "Основной трафик")}
    description={isPremium
      ? at(
          "user_premium_override_card_hint",
          {},
          "Безлимит и дополнительный объём для премиум-сквадов поверх тарифа."
        )
      : at(
          "user_regular_override_card_hint",
          {},
          "Безлимит и постоянный бонус к лимиту основного трафика."
        )}
  />
  <div class="admin-user-action-sheet-body admin-user-override-stack">
    <Label.Root class="admin-field-label admin-extend-field">
      <span>
        {isPremium
          ? at("user_premium_override_bonus", {}, "Доп. премиум-трафик, GB")
          : at("user_regular_override_bonus", {}, "Доп. основной трафик, GB")}
      </span>
      <small>
        {isPremium
          ? at("user_premium_override_bonus_hint", {}, "")
          : at("user_regular_override_bonus_hint", {}, "")}
      </small>
      <Input
        class="input"
        type="number"
        min="0"
        step="1"
        placeholder="0"
        value={bonusDraft}
        disabled={unlimitedDraft}
        aria-label={isPremium
          ? at("user_premium_override_bonus", {}, "Доп. премиум-трафик, GB")
          : at("user_regular_override_bonus", {}, "Доп. основной трафик, GB")}
        oninput={(event) => setBonus(event.currentTarget.value)}
      />
    </Label.Root>
  </div>
  <div class="admin-user-action-sheet-footer admin-override-card-footer">
    <div class="admin-override-card-toolbar">
      <label class="admin-override-unlimited-label">
        <Checkbox
          checked={unlimitedDraft}
          aria-label={at("user_override_unlimited_short", {}, "Безлимит")}
          onCheckedChange={setUnlimited}
        />
        <span>{at("user_override_unlimited_short", {}, "Безлимит")}</span>
      </label>
      <div class="admin-action-save-controls">
        {#if dirty}
          <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge>
        {/if}
        <AdminButton
          variant="primary"
          onclick={saveOverride}
          disabled={userActionBusy || !dirty || !draftValid}
        >
          {isPremium
            ? at("user_premium_override_save", {}, "Сохранить")
            : at("user_regular_override_save", {}, "Сохранить")}
        </AdminButton>
      </div>
    </div>
    <div class="admin-override-status-lines">
      {#if dirty}
        <span class="admin-unsaved-hint">
          {at("user_action_unsaved_hint", {}, "Есть несохранённые изменения")}
        </span>
      {/if}
      {#if !draftValid}
        <span class="admin-invalid-hint">
          {isPremium
            ? at("premium_override_invalid_bonus", {}, "Некорректное значение GB")
            : at(
                "regular_override_invalid_bonus",
                {},
                "Некорректное значение GB для основного трафика"
              )}
        </span>
      {/if}
      {#if unlimitedOverride}
        <span class="admin-meta-truncate">
          {isPremium
            ? at("user_premium_override_status_unlimited", {}, "Сейчас: безлимит")
            : at("user_regular_override_status_unlimited", {}, "Сейчас: безлимит")}
        </span>
      {:else if bonusBytes > 0}
        <span class="admin-meta-truncate">
          {isPremium
            ? at(
                "user_premium_override_status_bonus",
                { gb: bonusGb },
                `Премиум сейчас: +${bonusGb} GB`
              )
            : at(
                "user_regular_override_status_bonus",
                { gb: bonusGb },
                `Основной сейчас: +${bonusGb} GB`
              )}
        </span>
      {:else}
        <span class="admin-muted">
          {isPremium
            ? at("user_premium_override_status_none", {}, "Премиум-оверрайд не задан")
            : at("user_regular_override_status_none", {}, "Бонус основного трафика не задан")}
        </span>
      {/if}
    </div>
  </div>
</section>
