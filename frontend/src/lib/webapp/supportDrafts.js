const SUPPORT_DRAFT_STORAGE_PREFIX = "rw_webapp_support_draft_v1";
const SUPPORT_DRAFT_TTL_MS = 14 * 24 * 60 * 60 * 1000;
const DEFAULT_SCOPE = "anonymous";

function safeStorage() {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage || null;
  } catch (_error) {
    return null;
  }
}

function draftKey(kind, scope, id = "new") {
  return [
    SUPPORT_DRAFT_STORAGE_PREFIX,
    encodeURIComponent(String(kind || "draft")),
    encodeURIComponent(String(scope || DEFAULT_SCOPE)),
    encodeURIComponent(String(id || "new")),
  ].join(":");
}

function normalizeDraftEnvelope(value) {
  if (!value || typeof value !== "object") return null;
  const updatedAt = Number(value.updatedAt || 0);
  if (!updatedAt || Date.now() - updatedAt > SUPPORT_DRAFT_TTL_MS) return null;
  return value.draft && typeof value.draft === "object" ? value.draft : null;
}

export function supportDraftScope(user = {}) {
  const id = String(user?.user_id ?? user?.id ?? user?.telegram_id ?? "").trim();
  return id || DEFAULT_SCOPE;
}

export function readSupportDraft(kind, scope, id = "new") {
  const storage = safeStorage();
  if (!storage) return null;
  const key = draftKey(kind, scope, id);

  try {
    const raw = storage.getItem(key);
    if (!raw) return null;

    const draft = normalizeDraftEnvelope(JSON.parse(raw));
    if (!draft) storage.removeItem(key);
    return draft;
  } catch (_error) {
    try {
      storage.removeItem(key);
    } catch (_removeError) {
      void _removeError;
    }
    return null;
  }
}

export function writeSupportDraft(kind, scope, id = "new", draft = {}) {
  const storage = safeStorage();
  if (!storage) return;

  try {
    storage.setItem(
      draftKey(kind, scope, id),
      JSON.stringify({
        updatedAt: Date.now(),
        draft: draft && typeof draft === "object" ? draft : {},
      })
    );
  } catch (_error) {
    void _error;
  }
}

export function clearSupportDraft(kind, scope, id = "new") {
  const storage = safeStorage();
  if (!storage) return;

  try {
    storage.removeItem(draftKey(kind, scope, id));
  } catch (_error) {
    void _error;
  }
}
