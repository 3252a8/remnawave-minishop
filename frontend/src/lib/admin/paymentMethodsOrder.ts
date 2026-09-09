import type { PaymentMethodOrderOption } from "./stores/settingsStore";

export type PaymentMethodOrderItem = PaymentMethodOrderOption;

const LEGACY_PLATEGA_METHOD_IDS = new Set([
  "platega_sbp",
  "platega_card",
  "platega_crypto",
  "platega_international",
  "platega_all_methods",
]);

function normalizedId(value: unknown): string {
  return String(value || "")
    .trim()
    .toLowerCase();
}

function uniqueIds(values: Iterable<unknown>): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const id = normalizedId(value);
    if (!id || seen.has(id)) continue;
    seen.add(id);
    result.push(id);
  }
  return result;
}

function configuredIds(value: unknown, options: PaymentMethodOrderOption[]): string[] {
  const plategaIds = uniqueIds(
    options
      .filter(
        (option) => option.provider_id === "platega" && LEGACY_PLATEGA_METHOD_IDS.has(option.id)
      )
      .map((option) => option.id)
  );
  const rawIds = String(value || "")
    .split(",")
    .map(normalizedId)
    .filter(Boolean);
  return uniqueIds(rawIds.flatMap((id) => (id === "platega" ? plategaIds : [id])));
}

export function paymentMethodOrderItems(
  value: unknown,
  options: PaymentMethodOrderOption[]
): PaymentMethodOrderItem[] {
  const normalizedOptions = new Map<string, PaymentMethodOrderOption>();
  for (const option of options || []) {
    const id = normalizedId(option.id);
    if (!id || normalizedOptions.has(id)) continue;
    normalizedOptions.set(id, { ...option, id });
  }

  const ids = uniqueIds([
    ...configuredIds(value, [...normalizedOptions.values()]),
    ...normalizedOptions.keys(),
  ]);
  return ids.map(
    (id) =>
      normalizedOptions.get(id) || {
        id,
        label: id,
        provider_id: id,
        provider_label: id,
        enabled: false,
        admin_only: false,
        known: false,
      }
  );
}

export function reorderVisiblePaymentMethods(
  allItems: PaymentMethodOrderItem[],
  visibleItems: PaymentMethodOrderItem[],
  from: number,
  to: number
): PaymentMethodOrderItem[] {
  if (
    from === to ||
    from < 0 ||
    to < 0 ||
    from >= visibleItems.length ||
    to >= visibleItems.length
  ) {
    return allItems;
  }

  const reorderedVisible = [...visibleItems];
  const [moved] = reorderedVisible.splice(from, 1);
  if (!moved) return allItems;
  reorderedVisible.splice(to, 0, moved);

  const visibleIds = new Set(visibleItems.map((item) => item.id));
  let visibleIndex = 0;
  return allItems.map((item) =>
    visibleIds.has(item.id) ? reorderedVisible[visibleIndex++] || item : item
  );
}

export function serializePaymentMethodOrder(items: PaymentMethodOrderItem[]): string {
  return uniqueIds(items.map((item) => item.id)).join(",");
}
