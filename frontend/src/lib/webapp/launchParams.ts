/** Keep action namespaces out of invitation attribution, including stored values. */
export function referralStartParam(value: unknown): string {
  if (typeof value !== "string") return "";
  const raw = value.trim();
  if (
    /^(?:promo|plan|gift|ticket|admin|ext)_/i.test(raw) ||
    /^(?:home|plans|checkout|invite|partner|install|trial|devices|support|settings|notifications|security|status|admin|extensions|balance|gifts)$/i.test(
      raw
    ) ||
    /^[/#]/.test(raw)
  )
    return "";
  return raw;
}

export function extensionLaunchPath(value: unknown): string {
  if (typeof value !== "string" || !value.startsWith("ext_")) return "";
  const payload = value.slice(4);
  const separator = payload.lastIndexOf("__");
  if (separator < 0) return "";
  const owner = payload.slice(0, separator);
  const view = payload.slice(separator + 2);
  return /^[a-z][a-z0-9_-]{0,63}$/.test(owner) && /^[a-z][a-z0-9-]{1,63}$/.test(view)
    ? `/extensions/${owner}/${view}`
    : "";
}
