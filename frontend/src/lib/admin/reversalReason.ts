export function isReversalReasonValid(reason: string, withoutReason: boolean): boolean {
  return withoutReason || reason.trim().length >= 3;
}
