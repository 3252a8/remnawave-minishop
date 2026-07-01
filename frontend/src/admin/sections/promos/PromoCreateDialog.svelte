<script lang="ts">
  import { Input } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminButton, AdminField, AdminSelect } from "$components/patterns/admin/index.js";
  import PromoEffectSelector from "./PromoEffectSelector.svelte";
  import type { components } from "$lib/api/openapi.generated";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type PromoDraft = Omit<components["schemas"]["PromoCreateBody"], "valid_days"> & {
    valid_days: number;
  };
  type CreateNumberField =
    | "bonus_days"
    | "discount_percent"
    | "duration_multiplier"
    | "traffic_multiplier"
    | "min_subscription_months"
    | "min_traffic_gb"
    | "max_activations"
    | "valid_days";
  type PromoEffectKind =
    "bonus_days" | "discount_percent" | "duration_multiplier" | "traffic_multiplier";
  type ScopeItem = { value: string; label: string };

  type Props = {
    at: TranslateFn;
    draft: PromoDraft;
    effectKind: PromoEffectKind;
    onBonusRequiresPaymentChange: (checked: boolean) => void;
    onClose: () => void;
    onCodeInput: (code: string) => void;
    onCreate: () => void | Promise<void>;
    onEffectChange: (value: string) => void;
    onNumberInput: (field: CreateNumberField, value: string) => void;
    onScopeChange: (scope: string) => void;
    open: boolean;
    scopeItems: ScopeItem[];
    usesCheckout: boolean;
  };

  let {
    at,
    draft,
    effectKind,
    onBonusRequiresPaymentChange,
    onClose,
    onCodeInput,
    onCreate,
    onEffectChange,
    onNumberInput,
    onScopeChange,
    open,
    scopeItems,
    usesCheckout,
  }: Props = $props();

  function inputValue(event: Event): string {
    return (event.currentTarget as HTMLInputElement).value;
  }
</script>

<Dialog
  {open}
  title={at("promo_create_title", {}, "Create code")}
  closeLabel={at("close", {}, "Close")}
  onclose={onClose}
  class="admin-dialog admin-promo-dialog admin-promo-create-dialog"
>
  <div class="admin-promo-edit-body admin-promo-create-body" data-dialog-content>
    <div class="admin-promo-edit-summary">
      <div class="admin-promo-edit-summary-main">
        <span>{at("promo_label_code", {}, "Code")}</span>
        <strong>{draft.code || "AUTO"}</strong>
      </div>
      <div class="admin-promo-edit-summary-meta">
        <span class="admin-promo-edit-summary-uses">
          {draft.max_activations || 1}/{draft.max_activations || 1}
        </span>
      </div>
    </div>

    <div class="admin-promo-settings-grid">
      <section class="admin-editor-section admin-promo-editor-section admin-promo-basics-section">
        <header class="admin-editor-section-head">
          <div class="admin-editor-section-title">
            <strong>{at("promo_section_basics", {}, "Basics")}</strong>
          </div>
        </header>
        <div class="admin-promo-fields-grid admin-promo-basics-grid">
          <div class="admin-promo-field-shell">
            <AdminField label={at("promo_label_code", {}, "Code")}>
              <Input
                type="text"
                class="input"
                value={draft.code || ""}
                oninput={(event) => onCodeInput(inputValue(event))}
                placeholder="AUTO"
              />
            </AdminField>
          </div>
          <div class="admin-promo-field-shell">
            <AdminField label={at("promo_label_scope", {}, "Scope")}>
              <AdminSelect
                value={draft.applies_to || "all"}
                items={scopeItems}
                placeholder={at("promo_label_scope", {}, "Scope")}
                onValueChange={onScopeChange}
              />
            </AdminField>
          </div>
          <div class="admin-promo-field-shell">
            <AdminField label={at("promo_label_max_activations", {}, "Max uses")}>
              <Input
                type="number"
                class="input"
                min="1"
                value={String(draft.max_activations)}
                oninput={(event) => onNumberInput("max_activations", inputValue(event))}
              />
            </AdminField>
          </div>
          <div class="admin-promo-field-shell">
            <AdminField label={at("promo_label_valid_days", {}, "Valid days")}>
              <Input
                type="number"
                class="input"
                min="0"
                value={draft.valid_days ? String(draft.valid_days) : ""}
                oninput={(event) => onNumberInput("valid_days", inputValue(event))}
              />
            </AdminField>
          </div>
        </div>
      </section>

      <section class="admin-editor-section admin-promo-editor-section admin-promo-effect-section">
        <header class="admin-editor-section-head">
          <div class="admin-editor-section-title">
            <strong>{at("promo_col_effect", {}, "Effect")}</strong>
            <small>
              {at("promo_effect_single_hint", {}, "Choose one effect; values do not stack.")}
            </small>
          </div>
        </header>
        <PromoEffectSelector
          {at}
          value={effectKind}
          values={draft}
          bonusRequiresPayment={Boolean(draft.bonus_requires_payment)}
          onValueChange={onEffectChange}
          {onNumberInput}
          {onBonusRequiresPaymentChange}
        />
      </section>

      <section
        class="admin-editor-section admin-promo-editor-section admin-promo-eligibility-section"
      >
        <header class="admin-editor-section-head">
          <div class="admin-editor-section-title">
            <strong>{at("promo_col_eligibility", {}, "Eligibility")}</strong>
            <small>
              {usesCheckout
                ? at(
                    "promo_conditions_hint",
                    {},
                    "Optional minimum purchase requirements checked before the code can be applied."
                  )
                : at(
                    "promo_conditions_disabled_for_instant_bonus",
                    {},
                    "Instant bonus-day grants do not use purchase requirements."
                  )}
            </small>
          </div>
        </header>
        <div class="admin-promo-fields-grid admin-promo-eligibility-grid">
          <div class="admin-promo-field-shell">
            <AdminField label={at("promo_label_min_months", {}, "Min months")}>
              <Input
                type="number"
                class="input"
                min="1"
                disabled={!usesCheckout}
                value={draft.min_subscription_months == null
                  ? ""
                  : String(draft.min_subscription_months)}
                oninput={(event) => onNumberInput("min_subscription_months", inputValue(event))}
              />
            </AdminField>
          </div>
          <div class="admin-promo-field-shell">
            <AdminField label={at("promo_label_min_gb", {}, "Min GB")}>
              <Input
                type="number"
                class="input"
                min="0"
                step="0.01"
                disabled={!usesCheckout}
                value={draft.min_traffic_gb == null ? "" : String(draft.min_traffic_gb)}
                oninput={(event) => onNumberInput("min_traffic_gb", inputValue(event))}
              />
            </AdminField>
          </div>
        </div>
      </section>
    </div>

    <div class="admin-dialog-actions admin-promo-dialog-actions">
      <AdminButton onclick={onClose}>{at("btn_cancel", {}, "Cancel")}</AdminButton>
      <AdminButton variant="primary" onclick={onCreate}>
        {at("btn_create", {}, "Create")}
      </AdminButton>
    </div>
  </div>
</Dialog>
