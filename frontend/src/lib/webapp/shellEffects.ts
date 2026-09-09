import {
  reconcileBillingSelection,
  type BillingSelectionInput,
  type BillingSelectionState,
} from "./billingSelectionSync.js";

type ThemeEffectRecord = Record<string, unknown>;
type ThemeTokens = Record<string, unknown> & {
  color_scheme?: string;
  bg?: string;
};
type EmailAvatarSync = {
  sync(email: unknown, onAvatarUrl: (url: string) => void): void;
};

export function applyThemeDocumentEffects(
  effectiveThemeEntry: ThemeEffectRecord | null | undefined
) {
  if (typeof document === "undefined" || !effectiveThemeEntry?.tokens) return;
  const tokens = effectiveThemeEntry.tokens as ThemeTokens;
  const scheme = tokens?.color_scheme || "dark";
  document.documentElement.style.colorScheme = scheme;
  const bg = String(tokens?.bg || "");
  // Clearing is important for CSS-file themes: their --bg lives on the root
  // theme class and must not be masked by the previous token-backed theme.
  document.body.style.backgroundColor = bg;
}

/** Custom properties this module currently owns on the document element. */
const themeRootProperties = new Set<string>();
/** Theme classes this module currently owns on the document element. */
const themeRootClasses = new Set<string>();

/**
 * Mirrors the shell's theme tokens onto the document element. `.app-shell`
 * carries the same declarations inline, so nothing changes inside the shell;
 * what this fixes is everything outside it — the body text colour and surfaces
 * portalled to the body (admin popovers, tooltips), which would otherwise keep
 * resolving tokens from the static dark `:root` palette on a light theme.
 */
export function applyThemeRootTokens(inlineStyle: string, rootClass = "") {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  const applied = new Set<string>();
  for (const declaration of String(inlineStyle || "").split(";")) {
    const separator = declaration.indexOf(":");
    if (separator < 1) continue;
    const property = declaration.slice(0, separator).trim();
    const value = declaration.slice(separator + 1).trim();
    if (!property.startsWith("--") || !value) continue;
    root.style.setProperty(property, value);
    applied.add(property);
  }
  for (const property of themeRootProperties) {
    if (!applied.has(property)) root.style.removeProperty(property);
  }
  themeRootProperties.clear();
  for (const property of applied) themeRootProperties.add(property);

  const nextClasses = new Set(
    String(rootClass || "")
      .split(/\s+/)
      .map((value) => value.trim())
      .filter(Boolean)
  );
  for (const className of themeRootClasses) {
    if (!nextClasses.has(className)) root.classList.remove(className);
  }
  for (const className of nextClasses) root.classList.add(className);
  themeRootClasses.clear();
  for (const className of nextClasses) themeRootClasses.add(className);
}

export function closeDisabledEmailAuthDialogs({
  closeLinkEmailDialog,
  closeSetPasswordDialog,
  emailAuthEnabled,
  linkEmailOpen,
  setPasswordOpen,
}: {
  closeLinkEmailDialog: () => void;
  closeSetPasswordDialog: () => void;
  emailAuthEnabled: boolean;
  linkEmailOpen: boolean;
  setPasswordOpen: boolean;
}) {
  if (emailAuthEnabled) return;
  if (linkEmailOpen) closeLinkEmailDialog();
  if (setPasswordOpen) closeSetPasswordDialog();
}

export function syncShellBillingSelection({
  applyPatch,
  input,
  state,
}: {
  applyPatch: (patch: Partial<BillingSelectionState>) => void;
  input: BillingSelectionInput;
  state: BillingSelectionState;
}) {
  const patch = reconcileBillingSelection(state, input);
  if (patch) applyPatch(patch);
  return patch;
}

export function syncShellEmailAvatar({
  email,
  emailAvatarSync,
  setEmailAvatarUrl,
}: {
  email: unknown;
  emailAvatarSync: EmailAvatarSync;
  setEmailAvatarUrl: (url: string) => void;
}) {
  emailAvatarSync.sync(email, setEmailAvatarUrl);
}
