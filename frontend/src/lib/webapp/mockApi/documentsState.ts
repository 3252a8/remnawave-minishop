import type { DemoRecord } from "./dataset";

const STORAGE_KEY = "minishop-demo-documents";

export function loadDemoDocuments(): Map<string, DemoRecord> {
  const documents = new Map<string, DemoRecord>();
  try {
    if (typeof window === "undefined") return documents;
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    const values: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(values)) return documents;
    for (const value of values) {
      if (!value || typeof value !== "object" || Array.isArray(value)) continue;
      const document = value as DemoRecord;
      if (
        typeof document.slug !== "string" ||
        !document.slug ||
        typeof document.title !== "string" ||
        typeof document.markdown !== "string"
      )
        continue;
      documents.set(document.slug, document);
    }
  } catch {
    // Keep the demo usable when browser storage is unavailable or malformed.
  }
  return documents;
}

export function storeDemoDocuments(documents: ReadonlyMap<string, DemoRecord>): void {
  try {
    if (typeof window === "undefined") return;
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...documents.values()]));
  } catch {
    // Documents remain available in memory when browser storage is unavailable.
  }
}
