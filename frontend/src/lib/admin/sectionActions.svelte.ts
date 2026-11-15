/**
 * Page-header actions for sections whose dialogs live in the section itself
 * (gifts, plugins, partners, tariffs). The header asks; the mounted section
 * answers once and clears the request.
 */
export type SectionActionRequest = { section: string; action: string; id: number };

let current = $state<SectionActionRequest | null>(null);
let nextId = 0;

export function requestSectionAction(section: string, action: string): void {
  nextId += 1;
  current = { section, action, id: nextId };
}

/** Returns true once for a matching request; read it inside an `$effect`. */
export function takeSectionAction(section: string, action: string): boolean {
  const request = current;
  if (!request || request.section !== section || request.action !== action) return false;
  current = null;
  return true;
}
