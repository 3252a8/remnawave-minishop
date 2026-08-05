import type { SettingField, SettingsSection } from "./stores/settingsStore";

export type SettingsPath = string[];
export type AdminSettingField = SettingField &
  Record<string, unknown> & {
    subsection?: string;
    provider_id?: string;
    provider_info_url?: string;
    provider_label?: string;
    provider_logo_url?: string;
    webhook_path?: string;
    webhook_url?: string;
  };
export type AdminSettingsSection = Omit<SettingsSection, "fields"> & {
  fields: AdminSettingField[];
};
export type SettingsSubsection = {
  id: string;
  label: string | null;
  fields: AdminSettingField[];
  i18nLabelKey?: string | null;
  providerInfo?: GroupProviderInfo;
  webhook?: GroupWebhook;
};
export type SemanticFieldGroup = {
  id: string;
  titleKey: string;
  titleFallback: string;
  descriptionKey: string;
  descriptionFallback: string;
  fields: AdminSettingField[];
};
export type ResolvedSettingsPath = {
  section: AdminSettingsSection;
  group: SettingsSubsection | null;
  fieldGroup: SemanticFieldGroup | null;
  anchorKey: string;
};
export type GroupWebhook = {
  key: string;
  path: string;
  url: string;
  hintI18nKey?: string;
  hintFallback?: string;
  requiresBaseUrl?: boolean;
  baseConfigured?: boolean;
} | null;
export type GroupProviderInfo = {
  id: string;
  label: string;
  infoUrl: string;
  logoUrl: string;
  logoFallback: string;
} | null;

export const SETTINGS_SECTION_IDS_HIDDEN_IN_GENERAL_SETTINGS = new Set(["appearance", "pricing"]);

const PLATEGA_SBP_KEYS = new Set([
  "PLATEGA_SBP_ENABLED",
  "PLATEGA_SBP_ADMIN_ONLY_ENABLED",
  "PLATEGA_SBP_METHOD",
]);
const PLATEGA_CRYPTO_KEYS = new Set([
  "PLATEGA_CRYPTO_ENABLED",
  "PLATEGA_CRYPTO_ADMIN_ONLY_ENABLED",
  "PLATEGA_CRYPTO_METHOD",
]);
const PLATEGA_LEGACY_KEYS = new Set(["PLATEGA_PAYMENT_METHOD"]);
const WATA_FIAT_KEYS = new Set([
  "WATA_ENABLED",
  "WATA_ADMIN_ONLY_ENABLED",
  "WATA_API_TOKEN",
  "WATA_TERMINAL_ID",
  "WATA_TERMINAL_PUBLIC_ID",
  "WATA_RETURN_URL",
  "WATA_FAILED_URL",
  "WATA_LINK_TTL_MINUTES",
  "WATA_SUPPORTED_CURRENCIES",
]);
const WATA_CRYPTO_KEYS = new Set([
  "WATA_CRYPTO_ENABLED",
  "WATA_CRYPTO_ADMIN_ONLY_ENABLED",
  "WATA_CRYPTO_API_TOKEN",
  "WATA_CRYPTO_TERMINAL_ID",
  "WATA_CRYPTO_TERMINAL_PUBLIC_ID",
  "WATA_CRYPTO_RETURN_URL",
  "WATA_CRYPTO_FAILED_URL",
  "WATA_CRYPTO_LINK_TTL_MINUTES",
  "WATA_CRYPTO_SUPPORTED_CURRENCIES",
]);
const WATA_WEBHOOK_KEYS = new Set([
  "WATA_WEBHOOK_VERIFY_SIGNATURE",
  "WATA_PUBLIC_KEY",
  "WATA_CRYPTO_PUBLIC_KEY",
  "WATA_TRUSTED_IPS",
]);
const SEMANTIC_FIELD_GROUP_ORDER: Record<string, number> = {
  platega_common: 1,
  platega_sbp: 2,
  platega_crypto: 3,
  platega_legacy: 4,
  wata_common: 1,
  wata_fiat: 2,
  wata_crypto: 3,
  wata_webhook: 4,
};

export function normalizeSettingsPath(path: unknown): SettingsPath {
  const parts = Array.isArray(path) ? path : String(path || "").split("/");
  return parts
    .map((part) => String(part || "").trim())
    .filter(Boolean)
    .slice(0, 3);
}

export function settingsPathKey(path: unknown): string {
  return normalizeSettingsPath(path)
    .map((part) => settingsPathToken(part))
    .join("/");
}

export function settingsPathToken(value: unknown): string {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[_\s]+/g, "-")
    .replace(/[^a-z0-9-]+/g, "")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

export function compactSettingsPathToken(value: unknown): string {
  return settingsPathToken(value).replace(/-/g, "");
}

export function settingsPathMatches(segment: unknown, value: unknown): boolean {
  const segmentToken = settingsPathToken(segment);
  const valueToken = settingsPathToken(value);
  if (!segmentToken || !valueToken) return false;
  return (
    segmentToken === valueToken ||
    compactSettingsPathToken(segment) === compactSettingsPathToken(value)
  );
}

export function settingsRouteSegment(value: unknown): string {
  return encodeURIComponent(settingsPathToken(value) || String(value || "").trim());
}

export function settingsFieldGroupRouteSegment(
  group: SettingsSubsection | null | undefined,
  fieldGroup: SemanticFieldGroup | null | undefined
): string {
  const groupToken = settingsPathToken(group?.id);
  const fieldGroupToken = settingsPathToken(fieldGroup?.id);
  if (groupToken && fieldGroupToken.startsWith(`${groupToken}-`)) {
    return fieldGroupToken.slice(groupToken.length + 1);
  }
  return fieldGroupToken;
}

export function settingsSectionAnchorKey(sectionId: string): string {
  return `settings-section:${sectionId}`;
}

export function settingsSubsectionAnchorKey(sectionId: string, groupId: string): string {
  return `settings-subsection:${sectionId}:${groupId}`;
}

export function settingsFieldGroupAnchorKey(
  sectionId: string,
  groupId: string,
  fieldGroupId: string
): string {
  return `settings-field-group:${sectionId}:${groupId}:${fieldGroupId}`;
}

export function settingsFieldAnchorKey(fieldKey: string): string {
  return `settings-field:${fieldKey}`;
}

export function settingsSectionRoute(sectionId: string): SettingsPath {
  return [settingsRouteSegment(sectionId)].filter(Boolean);
}

export function settingsSubsectionRoute(sectionId: string, groupId: string): SettingsPath {
  return [settingsRouteSegment(sectionId), settingsRouteSegment(groupId)].filter(Boolean);
}

export function findSettingsSubsection(
  section: AdminSettingsSection,
  segment: unknown
): SettingsSubsection | undefined {
  return groupSectionFields(section).find(
    (group) => group.label && settingsPathMatches(segment, group.id)
  );
}

export function findSettingsFieldGroup(
  section: AdminSettingsSection,
  group: SettingsSubsection,
  segment: unknown
): SemanticFieldGroup | undefined {
  return semanticFieldGroups(section, group).find((fieldGroup) => {
    if (!fieldGroup.titleKey) return false;
    return [
      fieldGroup.id,
      fieldGroup.titleFallback,
      settingsFieldGroupRouteSegment(group, fieldGroup),
    ].some((value) => settingsPathMatches(segment, value));
  });
}

export function resolveSettingsPath(
  path: unknown,
  sections: AdminSettingsSection[]
): ResolvedSettingsPath | null {
  const [sectionSegment, subsectionSegment, fieldGroupSegment] = normalizeSettingsPath(path);
  if (!sectionSegment) return null;
  const section = sections.find((item) => settingsPathMatches(sectionSegment, item.id));
  if (!section) return null;

  let group = null;
  let fieldGroup = null;
  let anchorKey = settingsSectionAnchorKey(section.id);

  if (subsectionSegment) {
    group = findSettingsSubsection(section, subsectionSegment);
    if (group) {
      anchorKey = settingsSubsectionAnchorKey(section.id, group.id);
    }
  }

  if (group && fieldGroupSegment) {
    fieldGroup = findSettingsFieldGroup(section, group, fieldGroupSegment);
    if (fieldGroup) {
      anchorKey = settingsFieldGroupAnchorKey(section.id, group.id, fieldGroup.id);
    }
  }

  return { section, group: group ?? null, fieldGroup: fieldGroup ?? null, anchorKey };
}

export function settingsPathAnchorKey(path: unknown, target: ResolvedSettingsPath | null): string {
  const [sectionSegment, subsectionSegment, fieldGroupSegment] = normalizeSettingsPath(path);
  if (!target?.group || !fieldGroupSegment) return target?.anchorKey || "";
  const sectionToken = settingsPathToken(sectionSegment);
  const subsectionToken = compactSettingsPathToken(subsectionSegment);
  const fieldGroupToken = compactSettingsPathToken(fieldGroupSegment);
  if (sectionToken === "payments" && subsectionToken === "platega") {
    if (fieldGroupToken === "crypto" || fieldGroupToken === "plategacrypto") {
      return settingsFieldGroupAnchorKey("payments", "Platega", "platega_crypto");
    }
    if (
      fieldGroupToken === "sbp" ||
      fieldGroupToken === "card" ||
      fieldGroupToken === "plategasbp"
    ) {
      return settingsFieldGroupAnchorKey("payments", "Platega", "platega_sbp");
    }
  }
  if (sectionToken === "payments" && subsectionToken === "wata") {
    if (fieldGroupToken === "crypto" || fieldGroupToken === "watacrypto") {
      return settingsFieldGroupAnchorKey("payments", "Wata", "wata_crypto");
    }
    if (
      fieldGroupToken === "card" ||
      fieldGroupToken === "fiat" ||
      fieldGroupToken === "sbp" ||
      fieldGroupToken === "watafiat"
    ) {
      return settingsFieldGroupAnchorKey("payments", "Wata", "wata_fiat");
    }
    if (fieldGroupToken === "webhook" || fieldGroupToken === "webhooks") {
      return settingsFieldGroupAnchorKey("payments", "Wata", "wata_webhook");
    }
  }
  const fieldGroup = findSettingsFieldGroup(target.section, target.group, fieldGroupSegment);
  if (!fieldGroup) return target.anchorKey;
  return settingsFieldGroupAnchorKey(target.section.id, target.group.id, fieldGroup.id);
}

export function arrayValue(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : value ? [String(value)] : [];
}

export function normalizeWebhookPath(path: unknown): string {
  const normalized = String(path || "").trim();
  if (!normalized) return "";
  return normalized.startsWith("/") ? normalized : `/${normalized}`;
}

export function webhookUrlForField(field: AdminSettingField): string {
  const explicit = String(field?.webhook_url || "").trim();
  if (explicit) return explicit;
  const path = normalizeWebhookPath(field?.webhook_path);
  if (!path) return "";
  if (field?.webhook_requires_base_url && field?.webhook_base_url_configured === false) {
    return "";
  }
  if (typeof window !== "undefined" && window.location?.origin) {
    return `${window.location.origin}${path}`;
  }
  return path;
}

export function groupWebhook(fields: AdminSettingField[]): GroupWebhook {
  const field = (fields || []).find((item) => item.webhook_path || item.webhook_url);
  if (!field) return null;
  const path = normalizeWebhookPath(field.webhook_path);
  const url = webhookUrlForField(field);
  if (!url && !path) return null;
  return {
    key: `${String(field.provider_id || field.key || "provider")}:${path || url}`,
    path,
    url,
    requiresBaseUrl: Boolean(field.webhook_requires_base_url),
    baseConfigured: field.webhook_base_url_configured !== false,
    hintI18nKey: String(field.webhook_hint_i18n_key || ""),
    hintFallback: String(field.webhook_hint || ""),
  };
}

function providerLogoFallback(label: string): string {
  const words = label
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (words.length >= 2) {
    return words
      .slice(0, 2)
      .map((word) => word[0])
      .join("")
      .toUpperCase();
  }
  const compact = (words[0] || label).replace(/[^\p{L}\p{N}]+/gu, "");
  return compact.slice(0, 2).toUpperCase() || "P";
}

export function groupProviderInfo(fields: AdminSettingField[]): GroupProviderInfo {
  const field = (fields || []).find(
    (item) => item.provider_info_url || item.provider_logo_url || item.provider_label
  );
  if (!field) return null;
  const label = String(field.provider_label || field.subsection || field.provider_id || "").trim();
  const infoUrl = String(field.provider_info_url || "").trim();
  const logoUrl = String(field.provider_logo_url || "").trim();
  if (!label || (!infoUrl && !logoUrl)) return null;
  return {
    id: String(field.provider_id || label),
    label,
    infoUrl,
    logoUrl,
    logoFallback: providerLogoFallback(label),
  };
}

export function groupSectionFields(section: AdminSettingsSection): SettingsSubsection[] {
  const groups = new Map<string, SettingsSubsection>();
  for (const field of section.fields || []) {
    const key = field.subsection || "_root";
    if (!groups.has(key)) {
      groups.set(key, {
        id: key,
        label: key === "_root" ? null : key,
        fields: [],
        i18nLabelKey: String(field.i18n_subsection_key || "") || null,
      });
    }
    const group = groups.get(key);
    if (!group) continue;
    group.fields.push(field);
    if (!group.i18nLabelKey && field.i18n_subsection_key) {
      group.i18nLabelKey = String(field.i18n_subsection_key);
    }
  }
  return Array.from(groups.entries()).map(([id, group]) => ({
    id,
    label: id === "_root" ? null : id,
    i18nLabelKey: group.i18nLabelKey,
    providerInfo: groupProviderInfo(group.fields),
    webhook: groupWebhook(group.fields),
    fields: group.fields,
  }));
}

function fieldGroupMeta(
  id: string,
  titleKey: string,
  titleFallback: string,
  descriptionKey = "",
  descriptionFallback = ""
): Omit<SemanticFieldGroup, "fields"> {
  return { id, titleKey, titleFallback, descriptionKey, descriptionFallback };
}

function plategaSemanticGroup(field: AdminSettingField): Omit<SemanticFieldGroup, "fields"> | null {
  const key = String(field?.key || "");
  if (PLATEGA_SBP_KEYS.has(key) || key.startsWith("PAYMENT_PLATEGA_SBP_")) {
    return fieldGroupMeta(
      "platega_sbp",
      "settings_group_platega_sbp",
      "SBP/card button",
      "settings_group_platega_sbp_hint",
      "Visibility, method ID, and labels for the SBP/card payment button."
    );
  }
  if (PLATEGA_CRYPTO_KEYS.has(key) || key.startsWith("PAYMENT_PLATEGA_CRYPTO_")) {
    return fieldGroupMeta(
      "platega_crypto",
      "settings_group_platega_crypto",
      "Crypto button",
      "settings_group_platega_crypto_hint",
      "Visibility, method ID, and labels for the crypto payment button."
    );
  }
  if (PLATEGA_LEGACY_KEYS.has(key)) {
    return fieldGroupMeta(
      "platega_legacy",
      "settings_group_platega_legacy",
      "Legacy compatibility",
      "settings_group_platega_legacy_hint",
      "Fallback method for old Platega callbacks and deployments."
    );
  }
  return fieldGroupMeta(
    "platega_common",
    "settings_group_platega_common",
    "Common settings",
    "settings_group_platega_common_hint",
    "Shared merchant credentials, redirects, and API endpoint."
  );
}

function wataSemanticGroup(field: AdminSettingField): Omit<SemanticFieldGroup, "fields"> | null {
  const key = String(field?.key || "");
  if (WATA_WEBHOOK_KEYS.has(key)) {
    return fieldGroupMeta(
      "wata_webhook",
      "settings_group_wata_webhook",
      "Webhook verification",
      "settings_group_wata_webhook_hint",
      "Signature, public keys, trusted IPs, and the shared webhook URL."
    );
  }
  if (WATA_CRYPTO_KEYS.has(key) || key.startsWith("PAYMENT_WATA_CRYPTO_")) {
    return fieldGroupMeta(
      "wata_crypto",
      "settings_group_wata_crypto",
      "Crypto terminal",
      "settings_group_wata_crypto_hint",
      "Visibility, credentials, redirects, currencies, and labels for the crypto button."
    );
  }
  if (WATA_FIAT_KEYS.has(key) || key.startsWith("PAYMENT_WATA_")) {
    return fieldGroupMeta(
      "wata_fiat",
      "settings_group_wata_fiat",
      "Card/SBP terminal",
      "settings_group_wata_fiat_hint",
      "Visibility, credentials, redirects, currencies, and labels for the card/SBP button."
    );
  }
  return fieldGroupMeta(
    "wata_common",
    "settings_group_wata_common",
    "Common settings",
    "settings_group_wata_common_hint",
    "API endpoint shared by all Wata terminal profiles."
  );
}

function semanticFieldGroup(
  section: AdminSettingsSection,
  group: SettingsSubsection,
  field: AdminSettingField
): Omit<SemanticFieldGroup, "fields"> | null {
  if (section?.id === "payments" && group?.id === "Platega") {
    return plategaSemanticGroup(field);
  }
  if (section?.id === "payments" && group?.id === "Wata") {
    return wataSemanticGroup(field);
  }
  return null;
}

export function semanticFieldGroups(
  section: AdminSettingsSection,
  group: SettingsSubsection
): SemanticFieldGroup[] {
  const fields = group?.fields || [];
  const result = new Map<string, SemanticFieldGroup>();
  for (const field of fields) {
    const meta = semanticFieldGroup(section, group, field) || fieldGroupMeta("_default", "", "");
    if (!result.has(meta.id)) {
      result.set(meta.id, { ...meta, fields: [] });
    }
    const target = result.get(meta.id);
    if (target) target.fields.push(field);
  }
  return Array.from(result.values()).sort(
    (a, b) => (SEMANTIC_FIELD_GROUP_ORDER[a.id] || 999) - (SEMANTIC_FIELD_GROUP_ORDER[b.id] || 999)
  );
}
