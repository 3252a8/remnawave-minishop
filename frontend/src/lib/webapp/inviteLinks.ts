/** The bootstrap is available before authentication, including in the standalone Web App. */
export function inviteLinkPrefix(): string {
  if (typeof document === "undefined") return "discount";
  try {
    const config: unknown = JSON.parse(
      document.getElementById("webapp-config")?.textContent || "{}"
    );
    if (config && typeof config === "object" && "inviteLinkPrefix" in config) {
      const prefix = config.inviteLinkPrefix;
      if (typeof prefix === "string" && /^(?:[a-z][a-z0-9]{0,15})?$/.test(prefix)) return prefix;
    }
  } catch {
    // Default links also work before a bootstrap document is available.
  }
  return "discount";
}

export function decodeInvitationPayload(value: string): string {
  for (const prefix of new Set(["discount", inviteLinkPrefix()])) {
    if (!prefix || !value.startsWith(`${prefix}_`)) continue;
    const match = value.slice(prefix.length + 1).match(/^([rp])_([A-Za-z0-9_-]{1,43})$/);
    if (match) return match[1] === "r" ? `ref_u${match[2]}` : `p_${match[2]}`;
  }
  return value;
}

export function invitationQueryKeys(): string[] {
  return [...new Set(["discount", inviteLinkPrefix()])].filter(Boolean);
}
