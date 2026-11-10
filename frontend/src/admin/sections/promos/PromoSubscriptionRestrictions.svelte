<script lang="ts">
  import { AdminBadge, AdminField, AdminSelect } from "$components/patterns/admin/index.js";
  import { Input } from "$components/ui/index.js";

  type Restriction = "subscription_tariff_key" | "exact_subscription_days";

  let {
    at,
    tariffItems,
    tariffKey,
    durationDays,
    disabled,
    dirty = () => false,
    onTariffChange,
    onDurationChange,
  }: {
    at: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
    tariffItems: Array<{ value: string; label: string }>;
    tariffKey?: string | null;
    durationDays?: number | null;
    disabled: boolean;
    dirty?: (field: Restriction) => boolean;
    onTariffChange: (key: string | null) => void;
    onDurationChange: (days: number | null) => void;
  } = $props();

  const items = $derived([
    { value: "", label: at("promo_any_tariff") },
    ...tariffItems,
    ...(tariffKey && !tariffItems.some((item) => item.value === tariffKey)
      ? [{ value: tariffKey, label: tariffKey }]
      : []),
  ]);
</script>

<div class="admin-promo-field-shell" class:is-dirty={dirty("subscription_tariff_key")}>
  <AdminField label={at("promo_subscription_tariff")}>
    <AdminSelect
      {items}
      value={tariffKey ?? ""}
      ariaLabel={at("promo_subscription_tariff")}
      {disabled}
      onValueChange={(key) => onTariffChange(key || null)}
    />
  </AdminField>
  {#if dirty("subscription_tariff_key")}
    <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Changed")}</AdminBadge>
  {/if}
</div>
<div class="admin-promo-field-shell" class:is-dirty={dirty("exact_subscription_days")}>
  <AdminField label={at("promo_exact_subscription_days")}>
    <Input
      type="number"
      class="input"
      min="1"
      max="2147483647"
      placeholder={at("promo_any_duration")}
      {disabled}
      value={durationDays == null ? "" : String(durationDays)}
      oninput={(event) => {
        const control = event.currentTarget;
        onDurationChange(control.value === "" ? null : control.valueAsNumber);
      }}
    />
  </AdminField>
  {#if dirty("exact_subscription_days")}
    <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Changed")}</AdminBadge>
  {/if}
</div>
