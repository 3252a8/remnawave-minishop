export type PluralBucket = "one" | "few" | "many";

export function ruPlural<T extends string>(value: unknown, one: T, few: T, many: T): T {
  const n = Math.abs(Number(value || 0));
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

export function ruFractionAware<T extends string>(value: unknown, one: T, few: T, many: T): T {
  const n = Number(value || 0);
  if (!Number.isInteger(n)) return few;
  return ruPlural(n, one, few, many);
}

export function unitPluralBucket(value: unknown, lang: unknown): PluralBucket {
  if (String(lang || "").toLowerCase() === "ru") {
    const n = Number(value || 0);
    if (!Number.isInteger(n)) return "few";
    const abs = Math.abs(n);
    const mod10 = abs % 10;
    const mod100 = abs % 100;
    if (mod10 === 1 && mod100 !== 11) return "one";
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "few";
    return "many";
  }
  return Number(value) === 1 ? "one" : "many";
}
