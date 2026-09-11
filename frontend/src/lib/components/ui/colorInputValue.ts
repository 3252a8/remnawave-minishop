export function colorInputValueChanged(current: string, next: string): boolean {
  return current.trim().toLowerCase() !== next.trim().toLowerCase();
}
