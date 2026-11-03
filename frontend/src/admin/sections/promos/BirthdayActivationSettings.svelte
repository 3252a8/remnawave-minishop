<script lang="ts">
  import { onMount } from "svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminField,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import { Checkbox, Input } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import type { components } from "$lib/api/openapi.generated";
  import { getAdminApi } from "$lib/admin/context";
  import { adminErrorMessage } from "$lib/admin/errors.js";
  import { builtApiPath, unwrap } from "$lib/webapp/publicApi";
  import PromoEffectSelector from "./PromoEffectSelector.svelte";

  type Campaign = components["schemas"]["BirthdayActivationConfig"];
  type Effects = NonNullable<Campaign["effects"]>;
  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    at,
    scopeItems,
    initiallyOpen = false,
  }: {
    at: Translate;
    scopeItems: { value: string; label: string }[];
    initiallyOpen?: boolean;
  } = $props();

  const api = getAdminApi();
  const path = builtApiPath<"/api/admin/promos/birthday">("/admin/promos/birthday");
  let open = $state(false);
  let draft = $state<Campaign | null>(null);
  let enabled = $state<boolean | undefined>();
  let busy = $state(false);
  let error = $state("");
  const effectDefaults = {
    bonus_days: 7,
    regular_traffic_gb: 50,
    premium_traffic_gb: 20,
    discount_percent: 10,
    duration_multiplier: 2,
    traffic_multiplier: 2,
  };
  const disabledEffects = {
    bonus_days: 0,
    regular_traffic_gb: 0,
    premium_traffic_gb: 0,
    discount_percent: null,
    duration_multiplier: 1,
    traffic_multiplier: 1,
  };
  const emptyEffects: Effects = {
    ...disabledEffects,
    applies_to: "all",
    bonus_requires_payment: false,
    min_subscription_days: null,
    min_subscription_months: null,
    min_traffic_gb: null,
  };
  const effects = $derived({ ...emptyEffects, ...draft?.effects });

  onMount(() => {
    open = initiallyOpen;
    void load();
  });

  async function load(): Promise<void> {
    if (busy) return;
    busy = true;
    error = "";
    draft = null;
    try {
      draft = unwrap(await api(path)).campaign;
      enabled = Boolean(draft.enabled);
    } catch (cause) {
      error = adminErrorMessage(cause, at, at("promo_birthday_load_error"));
    } finally {
      busy = false;
    }
  }

  function updateEffects(patch: Partial<Effects>): void {
    if (draft) draft.effects = { ...effects, ...patch };
  }

  function toggleEffect(key: keyof typeof effectDefaults, checked: boolean): void {
    updateEffects({ [key]: checked ? effectDefaults[key] : disabledEffects[key] });
    if (!effects.bonus_days && !effects.regular_traffic_gb && !effects.premium_traffic_gb) {
      updateEffects({ bonus_requires_payment: false });
    }
  }

  async function save(): Promise<void> {
    if (!draft || busy) return;
    busy = true;
    error = "";
    try {
      const result = unwrap(await api(path, { method: "PUT", body: JSON.stringify(draft) }));
      enabled = Boolean(result.campaign.enabled);
      open = false;
    } catch (cause) {
      error = adminErrorMessage(cause, at, at("promo_birthday_save_error"));
    } finally {
      busy = false;
    }
  }
</script>

<section class="admin-editor-section" id="birthday-activation-settings">
  <header class="admin-editor-section-head">
    <div class="admin-editor-section-title">
      <strong>{at("promo_birthday_title")}</strong>
      <small>{at("promo_birthday_hint")}</small>
    </div>
    {#if enabled !== undefined}
      <AdminBadge>{enabled ? at("badge_active") : at("status_disabled")}</AdminBadge>
    {/if}
  </header>
  <AdminButton
    onclick={() => {
      open = true;
      void load();
    }}
  >
    {at("promo_birthday_configure")}
  </AdminButton>
</section>

<Dialog
  {open}
  title={at("promo_birthday_title")}
  closeLabel={at("close", {}, "Close")}
  onclose={() => {
    open = false;
  }}
  class="admin-dialog admin-promo-dialog admin-promo-create-dialog"
>
  <div class="admin-promo-edit-body admin-promo-create-body" data-dialog-content>
    {#if error}
      <p role="alert">{error}</p>
    {/if}
    {#if draft}
      <div class="admin-promo-settings-grid">
        <section class="admin-editor-section admin-promo-editor-section admin-promo-basics-section">
          <header class="admin-editor-section-head">
            <div class="admin-editor-section-title">
              <strong>{at("promo_birthday_delivery")}</strong>
              <small>{at("promo_birthday_delivery_hint")}</small>
            </div>
          </header>
          <label>
            <Checkbox
              ariaLabel={at("promo_birthday_enabled")}
              checked={Boolean(draft.enabled)}
              onCheckedChange={(checked) => {
                if (draft) draft.enabled = checked === true;
              }}
            />
            {at("promo_birthday_enabled")}
          </label>
          <AdminField label={at("promo_birthday_valid_days")}>
            <Input
              type="number"
              min="1"
              max="365"
              step="1"
              aria-label={at("promo_birthday_valid_days")}
              value={draft.valid_days ?? 7}
              oninput={(event) => {
                if (draft) draft.valid_days = Number(event.currentTarget.value);
              }}
            />
          </AdminField>
          <AdminField label={at("promo_label_scope")}>
            <AdminSelect
              value={effects.applies_to || "all"}
              items={scopeItems}
              ariaLabel={at("promo_label_scope")}
              onValueChange={(value) => updateEffects({ applies_to: value })}
            />
          </AdminField>
        </section>
        <section class="admin-editor-section admin-promo-editor-section admin-promo-effect-section">
          <header class="admin-editor-section-head">
            <div class="admin-editor-section-title">
              <strong>{at("promo_col_effect")}</strong>
              <small>{at("promo_effect_multiple_hint")}</small>
            </div>
          </header>
          <PromoEffectSelector
            {at}
            values={effects}
            bonusRequiresPayment={Boolean(effects.bonus_requires_payment)}
            onEnabledChange={toggleEffect}
            onNumberInput={(key, value) =>
              updateEffects({
                [key]: value === "" ? disabledEffects[key] : Number(value),
              })}
            onBonusRequiresPaymentChange={(checked) =>
              updateEffects({ bonus_requires_payment: checked })}
          />
        </section>
      </div>
      <div class="admin-dialog-actions admin-promo-dialog-actions">
        <AdminButton
          onclick={() => {
            open = false;
          }}>{at("btn_cancel")}</AdminButton
        >
        <AdminButton variant="primary" disabled={busy} onclick={save}>{at("save")}</AdminButton>
      </div>
    {:else if busy}
      <p role="status">{at("loading")}</p>
    {:else}
      <AdminButton onclick={load}>{at("refresh")}</AdminButton>
    {/if}
  </div>
</Dialog>
