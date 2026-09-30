/** Keep action namespaces out of invitation attribution, including stored values. */
export function referralStartParam(value: unknown): string {
  if (typeof value !== "string") return "";
  const raw = value.trim();
  if (
    /^(?:promo|plan|gift|ticket|admin)_/i.test(raw) ||
    /^(?:home|plans|checkout|invite|partner|install|trial|devices|support|settings|notifications|security|status|admin|extensions|balance|gifts)$/i.test(
      raw
    ) ||
    /^[/#]/.test(raw)
  )
    return "";
  return raw;
}
