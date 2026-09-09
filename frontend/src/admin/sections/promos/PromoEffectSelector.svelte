<script lang="ts">
  import { AdminBadge, AdminField } from "$components/patterns/admin/index.js";
  import { Checkbox, Input } from "$components/ui/index.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type PromoEffectKind =
    | "bonus_days"
    | "regular_traffic_gb"
    | "premium_traffic_gb"
    | "discount_percent"
    | "duration_multiplier"
    | "traffic_multiplier";
  type EffectValues = {
    bonus_days?: number | null;
    regular_traffic_gb?: number | null;
    premium_traffic_gb?: number | null;
    discount_percent?: number | null;
    duration_multiplier?: number | null;
    traffic_multiplier?: number | null;
  };

  let {
    at,
    values,
    dirtyFields = {},
    bonusRequiresPayment = false,
    bonusModeDirty = false,
    onEnabledChange,
    onNumberInput,
    onBonusRequiresPaymentChange = () => {},
  }: {
    at: TranslateFn;
    values: EffectValues;
    dirtyFields?: Partial<Record<PromoEffectKind, boolean>>;
    bonusRequiresPayment?: boolean;
    bonusModeDirty?: boolean;
    onEnabledChange: (kind: PromoEffectKind, checked: boolean) => void;
    onNumberInput: (field: PromoEffectKind, value: string) => void;
    onBonusRequiresPaymentChange?: (checked: boolean) => void;
  } = $props();

  const effectOptions = $derived([
    {
      kind: "bonus_days",
      title: at("promo_effect_bonus_days_title", {}, "Bonus days"),
      hint: at("promo_effect_bonus_days_hint", {}, "Adds days to the user's subscription."),
      example: at(
        "promo_effect_bonus_days_example",
        {},
        "Example: 10 adds 10 days immediately or after payment, depending on grant mode."
      ),
    },
    {
      kind: "discount_percent",
      title: at("promo_effect_discount_title", {}, "Discount"),
      hint: at("promo_effect_discount_hint", {}, "Reduces the checkout amount before payment."),
      example: at("promo_effect_discount_example", {}, "Example: 15% changes 1000 to 850."),
    },
    {
      kind: "regular_traffic_gb",
      title: at("promo_effect_regular_traffic_title", {}, "Regular traffic"),
      hint: at(
        "promo_effect_regular_traffic_hint",
        {},
        "Credits persistent regular top-up traffic that remains until used."
      ),
      example: at("promo_effect_regular_traffic_example", {}, "Example: 50 adds 50 GB."),
    },
    {
      kind: "premium_traffic_gb",
      title: at("promo_effect_premium_traffic_title", {}, "Premium traffic"),
      hint: at(
        "promo_effect_premium_traffic_hint",
        {},
        "Credits persistent premium top-up traffic for premium-enabled tariffs."
      ),
      example: at("promo_effect_premium_traffic_example", {}, "Example: 20 adds 20 GB."),
    },
    {
      kind: "duration_multiplier",
      title: at("promo_effect_duration_title", {}, "Duration multiplier"),
      hint: at("promo_effect_duration_hint", {}, "Multiplies paid subscription duration."),
      example: at("promo_effect_duration_example", {}, "Example: x2 turns 1 month into 2."),
    },
    {
      kind: "traffic_multiplier",
      title: at("promo_effect_traffic_title", {}, "Traffic multiplier"),
      hint: at(
        "promo_effect_traffic_hint",
        {},
        "Multiplies the traffic amount in a traffic purchase."
      ),
      example: at("promo_effect_traffic_example", {}, "Example: x2 turns 100 GB into 200 GB."),
    },
  ] as Array<{ kind: PromoEffectKind; title: string; hint: string; example: string }>);

  function inputValue(event: Event): string {
    return (event.currentTarget as HTMLInputElement).value;
  }

  function fieldLabel(kind: PromoEffectKind): string {
    if (kind === "bonus_days") return at("promo_label_bonus_days", {}, "Bonus days");
    if (kind === "regular_traffic_gb") {
      return at("promo_label_regular_traffic_gb", {}, "Regular traffic, GB");
    }
    if (kind === "premium_traffic_gb") {
      return at("promo_label_premium_traffic_gb", {}, "Premium traffic, GB");
    }
    if (kind === "discount_percent") return at("promo_label_discount", {}, "Discount %");
    if (kind === "duration_multiplier") {
      return at("promo_label_duration_multiplier", {}, "Duration x");
    }
    return at("promo_label_traffic_multiplier", {}, "Traffic x");
  }

  function fieldValue(kind: PromoEffectKind): string {
    if (kind === "bonus_days") return String(values.bonus_days || 7);
    if (kind === "regular_traffic_gb") return String(values.regular_traffic_gb || 50);
    if (kind === "premium_traffic_gb") return String(values.premium_traffic_gb || 20);
    if (kind === "discount_percent") {
      return values.discount_percent == null ? "10" : String(values.discount_percent);
    }
    if (kind === "duration_multiplier") {
      return values.duration_multiplier == null ? "2" : String(values.duration_multiplier);
    }
    return values.traffic_multiplier == null ? "2" : String(values.traffic_multiplier);
  }

  function minValue(kind: PromoEffectKind): string {
    if (kind === "bonus_days") return "1";
    if (kind === "regular_traffic_gb" || kind === "premium_traffic_gb") return "0.001";
    if (kind === "discount_percent") return "0.01";
    return "1.001";
  }

  function stepValue(kind: PromoEffectKind): string | undefined {
    if (kind === "bonus_days") return undefined;
    if (kind === "discount_percent") return "0.01";
    return "0.001";
  }

  function maxValue(kind: PromoEffectKind): string | undefined {
    if (kind === "discount_percent") return "100";
    if (kind === "regular_traffic_gb" || kind === "premium_traffic_gb") return "1000000";
    return undefined;
  }

  function isEnabled(kind: PromoEffectKind): boolean {
    const raw = Number(values[kind] || 0);
    if (kind === "duration_multiplier" || kind === "traffic_multiplier") return raw > 1;
    return raw > 0;
  }

  function isFixedGrantKind(kind: PromoEffectKind): boolean {
    return kind === "bonus_days" || kind === "regular_traffic_gb" || kind === "premium_traffic_gb";
  }

  function hasFixedGrant(): boolean {
    return (
      isEnabled("bonus_days") || isEnabled("regular_traffic_gb") || isEnabled("premium_traffic_gb")
    );
  }

  function hasCheckoutEffect(): boolean {
    return (
      isEnabled("discount_percent") ||
      isEnabled("duration_multiplier") ||
      isEnabled("traffic_multiplier")
    );
  }

  function fixedGrantRequiresCheckout(): boolean {
    return bonusRequiresPayment || (hasFixedGrant() && hasCheckoutEffect());
  }

  function isIncompatible(kind: PromoEffectKind): boolean {
    if (isEnabled(kind)) return false;
    if (kind === "traffic_multiplier") return hasFixedGrant();
    return isFixedGrantKind(kind) && isEnabled("traffic_multiplier");
  }

  function toggleBonusRequiresPayment(checked: boolean): void {
    onBonusRequiresPaymentChange(checked);
  }
</script>

<div class="admin-promo-effect-options">
  {#each effectOptions as option (option.kind)}
    <div
      class="admin-promo-effect-row"
      class:is-selected={isEnabled(option.kind)}
      class:is-dirty={dirtyFields[option.kind]}
    >
      <Checkbox
        checked={isEnabled(option.kind)}
        disabled={isIncompatible(option.kind)}
        ariaLabel={option.title}
        onCheckedChange={(checked) => onEnabledChange(option.kind, checked)}
      />
      <div class="admin-promo-effect-copy">
        <strong>
          {option.title}
          {#if dirtyFields[option.kind]}
            <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Changed")}</AdminBadge>
          {/if}
        </strong>
        <small>{option.hint}</small>
        <span>
          {isIncompatible(option.kind)
            ? at(
                "promo_effect_fixed_traffic_multiplier_incompatible",
                {},
                "Fixed grants cannot be combined with a traffic multiplier."
              )
            : option.example}
        </span>
      </div>
      <div class="admin-promo-effect-input">
        <AdminField label={fieldLabel(option.kind)}>
          <Input
            type="number"
            class="input"
            min={minValue(option.kind)}
            max={maxValue(option.kind)}
            step={stepValue(option.kind)}
            value={fieldValue(option.kind)}
            disabled={isIncompatible(option.kind)}
            onfocus={() => {
              if (!isEnabled(option.kind)) onEnabledChange(option.kind, true);
            }}
            oninput={(e) => {
              if (!isEnabled(option.kind)) onEnabledChange(option.kind, true);
              onNumberInput(option.kind, inputValue(e));
            }}
          />
        </AdminField>
      </div>
    </div>
  {/each}
  <div class="admin-promo-effect-mode" class:is-dirty={bonusModeDirty}>
    <label class="admin-promo-effect-mode-line">
      <Checkbox
        checked={fixedGrantRequiresCheckout()}
        disabled={hasFixedGrant() && hasCheckoutEffect()}
        ariaLabel={at("promo_bonus_mode_payment", {}, "Grant fixed bonuses after payment")}
        onCheckedChange={toggleBonusRequiresPayment}
      />
      <span class="admin-promo-effect-mode-label">
        {at("promo_bonus_mode_payment", {}, "Grant fixed bonuses after payment")}
      </span>
      <small>
        {fixedGrantRequiresCheckout()
          ? at(
              "promo_bonus_mode_payment_hint",
              {},
              "Days and fixed traffic are granted after a paid subscription purchase."
            )
          : at(
              "promo_bonus_mode_instant_hint",
              {},
              "Days and fixed traffic are granted immediately when the code is activated."
            )}
      </small>
    </label>
    {#if bonusModeDirty}
      <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Changed")}</AdminBadge>
    {/if}
  </div>
</div>

<style>
  .admin-promo-effect-options {
    display: grid;
    gap: 8px;
    max-width: 100%;
    min-width: 0;
  }

  .admin-promo-effect-row {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) minmax(160px, 220px);
    align-items: center;
    gap: 12px;
    min-width: 0;
    padding: 10px 12px;
    border: 1px solid var(--admin-border);
    border-radius: 8px;
    background: var(--admin-surface-2);
    cursor: pointer;
    transition:
      border-color 0.14s ease,
      background 0.14s ease;
  }

  .admin-promo-effect-row:hover,
  .admin-promo-effect-row.is-selected {
    border-color: var(--accent);
  }

  .admin-promo-effect-row.is-dirty {
    border-color: color-mix(in srgb, var(--warning) 70%, var(--admin-border));
    background: color-mix(in srgb, var(--warning) 8%, var(--admin-surface-2));
  }

  .admin-promo-effect-row.is-selected {
    background: color-mix(in srgb, var(--accent) 9%, var(--admin-surface-2));
  }

  .admin-promo-effect-copy {
    display: grid;
    gap: 3px;
    min-width: 0;
  }

  .admin-promo-effect-copy strong {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    color: var(--admin-text);
    font-size: 13px;
    line-height: 1.2;
  }

  .admin-promo-effect-copy small,
  .admin-promo-effect-copy span {
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.35;
  }

  .admin-promo-effect-copy span {
    color: color-mix(in srgb, var(--admin-muted) 80%, var(--admin-text));
  }

  .admin-promo-effect-input {
    min-width: 0;
  }

  .admin-promo-effect-mode {
    display: flex;
    align-items: center;
    grid-column: 1 / -1;
    gap: 8px;
    max-width: 100%;
    min-width: 0;
    padding: 6px 8px;
    border: 1px solid transparent;
    border-radius: 8px;
    background: color-mix(in srgb, var(--accent) 5%, transparent);
  }

  .admin-promo-effect-mode.is-dirty {
    border-color: color-mix(in srgb, var(--warning) 64%, var(--admin-border));
    background: color-mix(in srgb, var(--warning) 7%, transparent);
  }

  .admin-promo-effect-mode-line {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    flex: 1 1 auto;
    color: var(--admin-text);
  }

  .admin-promo-effect-mode-label {
    flex: 0 0 auto;
    color: var(--admin-text);
    font-size: 13px;
    font-weight: 650;
    line-height: 1.25;
  }

  .admin-promo-effect-mode small {
    min-width: 0;
    overflow: hidden;
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.35;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-promo-effect-mode :global(.admin-badge) {
    flex: 0 0 auto;
  }

  @media (max-width: 720px) {
    .admin-promo-effect-row {
      grid-template-columns: auto minmax(0, 1fr);
    }

    .admin-promo-effect-input {
      grid-column: 2;
    }

    .admin-promo-effect-mode {
      align-items: stretch;
      flex-direction: column;
    }

    .admin-promo-effect-mode-line {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      align-items: flex-start;
      width: 100%;
    }

    .admin-promo-effect-mode-label {
      min-width: 0;
    }

    .admin-promo-effect-mode small {
      grid-column: 2;
      white-space: normal;
    }

    .admin-promo-effect-mode :global(.admin-badge) {
      align-self: flex-start;
    }
  }
</style>
