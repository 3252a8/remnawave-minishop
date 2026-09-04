export type BalanceTarget = "user" | "partner";
export type BalanceAdjustmentMode = "add" | "subtract" | "set";

export function balanceTargetAvailable(
  target: BalanceTarget,
  userEnabled: boolean,
  partnerAdjustable: boolean
): boolean {
  return target === "user" ? userEnabled : partnerAdjustable;
}

export function resolveBalanceTarget(
  current: BalanceTarget,
  userEnabled: boolean,
  partnerAdjustable: boolean
): BalanceTarget | null {
  if (balanceTargetAvailable(current, userEnabled, partnerAdjustable)) return current;
  if (userEnabled) return "user";
  if (partnerAdjustable) return "partner";
  return null;
}

export function defaultBalanceTarget(
  userEnabled: boolean,
  partnerAdjustable: boolean
): BalanceTarget {
  return !userEnabled && partnerAdjustable ? "partner" : "user";
}

export function balanceAdjustmentAmountMinor(value: string, amountFactor: number): number | null {
  if (!value.trim()) return null;
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount < 0) return null;
  return Math.round(amount * amountFactor);
}

export function balanceAdjustmentValid({
  amountFactor,
  currentAmountMinor,
  mode,
  targetAvailable,
  value,
}: {
  amountFactor: number;
  currentAmountMinor: number;
  mode: BalanceAdjustmentMode;
  targetAvailable: boolean;
  value: string;
}): boolean {
  if (!targetAvailable) return false;
  const amountMinor = balanceAdjustmentAmountMinor(value, amountFactor);
  if (amountMinor === null) return false;
  if (mode !== "set" && amountMinor <= 0) return false;
  return mode !== "subtract" || amountMinor <= Math.max(0, currentAmountMinor);
}
