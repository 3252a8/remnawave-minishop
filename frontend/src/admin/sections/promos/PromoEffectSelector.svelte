<script lang="ts">
  import { AdminBadge, AdminField } from "$components/patterns/admin/index.js";
  import { Input, RadioGroup, RadioGroupItem } from "$components/ui/index.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type PromoEffectKind =
    "bonus_days" | "discount_percent" | "duration_multiplier" | "traffic_multiplier";
  type EffectValues = {
    bonus_days?: number | null;
    discount_percent?: number | null;
    duration_multiplier?: number | null;
    traffic_multiplier?: number | null;
  };

  let {
    at,
    value,
    values,
    dirtyFields = {},
    onValueChange,
    onNumberInput,
  }: {
    at: TranslateFn;
    value: PromoEffectKind;
    values: EffectValues;
    dirtyFields?: Partial<Record<PromoEffectKind, boolean>>;
    onValueChange: (value: string) => void;
    onNumberInput: (field: PromoEffectKind, value: string) => void;
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
    if (kind === "discount_percent") return at("promo_label_discount", {}, "Discount %");
    if (kind === "duration_multiplier") {
      return at("promo_label_duration_multiplier", {}, "Duration x");
    }
    return at("promo_label_traffic_multiplier", {}, "Traffic x");
  }

  function fieldValue(kind: PromoEffectKind): string {
    if (kind === "bonus_days") return String(values.bonus_days || 1);
    if (kind === "discount_percent") {
      return values.discount_percent == null ? "" : String(values.discount_percent);
    }
    if (kind === "duration_multiplier") {
      return values.duration_multiplier == null ? "" : String(values.duration_multiplier);
    }
    return values.traffic_multiplier == null ? "" : String(values.traffic_multiplier);
  }

  function minValue(kind: PromoEffectKind): string {
    if (kind === "bonus_days") return "1";
    if (kind === "discount_percent") return "0.01";
    return "1.001";
  }

  function stepValue(kind: PromoEffectKind): string | undefined {
    if (kind === "bonus_days") return undefined;
    if (kind === "discount_percent") return "0.01";
    return "0.001";
  }

  function maxValue(kind: PromoEffectKind): string | undefined {
    return kind === "discount_percent" ? "100" : undefined;
  }

  function selectKind(kind: PromoEffectKind): void {
    onValueChange(kind);
  }
</script>

<RadioGroup class="admin-promo-effect-options" {value} {onValueChange}>
  {#each effectOptions as option (option.kind)}
    <div
      class="admin-promo-effect-row"
      class:is-selected={value === option.kind}
      class:is-dirty={dirtyFields[option.kind]}
      onclick={() => selectKind(option.kind)}
      role="presentation"
    >
      <RadioGroupItem
        class="admin-promo-effect-radio"
        value={option.kind}
        ariaLabel={option.title}
      />
      <div class="admin-promo-effect-copy">
        <strong>
          {option.title}
          {#if dirtyFields[option.kind]}
            <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Changed")}</AdminBadge>
          {/if}
        </strong>
        <small>{option.hint}</small>
        <span>{option.example}</span>
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
            onfocus={() => selectKind(option.kind)}
            oninput={(e) => {
              selectKind(option.kind);
              onNumberInput(option.kind, inputValue(e));
            }}
          />
        </AdminField>
      </div>
    </div>
  {/each}
</RadioGroup>

<style>
  :global(.ui-radio-group.admin-promo-effect-options) {
    display: grid;
    gap: 8px;
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
    border-color: color-mix(in srgb, var(--warning, #f59e0b) 70%, var(--admin-border));
    background: color-mix(in srgb, var(--warning, #f59e0b) 8%, var(--admin-surface-2));
  }

  .admin-promo-effect-row.is-selected {
    background: color-mix(in srgb, var(--accent) 9%, var(--admin-surface-2));
  }

  :global(.ui-radio-item.admin-promo-effect-radio) {
    margin-top: 1px;
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

  @media (max-width: 720px) {
    .admin-promo-effect-row {
      grid-template-columns: auto minmax(0, 1fr);
    }

    .admin-promo-effect-input {
      grid-column: 2;
    }
  }
</style>
