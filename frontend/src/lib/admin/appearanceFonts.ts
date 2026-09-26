import { firstFontFamily } from "$lib/webapp/themeStyle";

import type { FontOption } from "./appearanceOptions";

/**
 * Keeps an authored font stack selectable without showing the same family twice.
 * A matching bundled option keeps its localized label while preserving the exact
 * stack, including its custom fallback chain.
 */
export function fontItemsWithCurrent(
  items: FontOption[],
  value: unknown,
  customLabel: string
): FontOption[] {
  const currentValue = String(value ?? "");
  if (!currentValue || items.some((item) => item.value === currentValue)) return items;

  const currentFamily = firstFontFamily(currentValue).toLowerCase();
  const matchingItem = items.find(
    (item) => firstFontFamily(item.value).toLowerCase() === currentFamily
  );
  if (matchingItem) {
    return items.map((item) => (item === matchingItem ? { ...item, value: currentValue } : item));
  }

  return [
    {
      value: currentValue,
      label: `${customLabel}: ${firstFontFamily(currentValue) || currentValue}`,
    },
    ...items,
  ];
}
