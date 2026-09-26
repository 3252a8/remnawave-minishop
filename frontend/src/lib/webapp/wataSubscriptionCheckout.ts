export function isWataSubscriptionMethod(method: unknown): boolean {
  return String(method || "").toLowerCase() === "wata_subscription";
}

function normalizedPhone(phone: string): string {
  let normalized = phone.replace(/[\s()\-.]/g, "");
  if (normalized.startsWith("00")) normalized = `+${normalized.slice(2)}`;
  if (!normalized.startsWith("+") && /^\d+$/.test(normalized)) normalized = `+${normalized}`;
  return normalized;
}

export function wataSubscriptionContacts(method: unknown, email: string, phone: string) {
  if (!isWataSubscriptionMethod(method)) return {};
  return { payerEmail: email.trim(), payerPhone: normalizedPhone(phone) };
}

export function wataSubscriptionContactsValid(
  method: unknown,
  email: string,
  phone: string
): boolean {
  if (!isWataSubscriptionMethod(method)) return true;
  return (
    /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) &&
    /^\+[1-9]\d{7,14}$/.test(normalizedPhone(phone))
  );
}
