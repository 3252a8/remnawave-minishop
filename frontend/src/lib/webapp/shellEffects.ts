import {
  reconcileBillingSelection,
  type BillingSelectionInput,
  type BillingSelectionState,
} from "./billingSelectionSync.js";

type ThemeEffectRecord = Record<string, unknown>;
type EmailAvatarSync = {
  sync(email: unknown, onAvatarUrl: (url: string) => void): void;
};

export function applyThemeDocumentEffects(
  effectiveThemeEntry: ThemeEffectRecord | null | undefined,
) {
  if (typeof document === "undefined" || !effectiveThemeEntry?.tokens) return;
  const scheme = effectiveThemeEntry.tokens.color_scheme || "dark";
  document.documentElement.style.colorScheme = scheme;
  const bg = effectiveThemeEntry.tokens.bg;
  if (bg) document.body.style.backgroundColor = bg;
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
