/** Display names of payment providers, shared by the admin and the cabinet. */
export const PAYMENT_PROVIDER_NAMES = {
  cryptopay: "CryptoPay",
  freekassa: "FreeKassa",
  heleket: "Heleket",
  lava: "LAVA",
  paykilla: "PayKilla",
  platega: "Platega",
  platega_all_methods: "Platega All methods",
  platega_card: "Platega Card",
  platega_crypto: "Platega Crypto",
  platega_international: "Platega International",
  platega_sbp: "Platega SBP/card",
  rivarapay_crypto: "RivaraPay Crypto",
  rivarapay_sbp: "RivaraPay SBP",
  rollypay: "RollyPay All methods",
  rollypay_card: "RollyPay Card",
  rollypay_crypto: "RollyPay Crypto",
  rollypay_international: "RollyPay International",
  rollypay_sbp: "RollyPay SBP",
  rollypay_subscription: "RollyPay Subscription",
  severpay: "SeverPay",
  stars: "Telegram Stars",
  telegram_stars: "Telegram Stars",
  wata: "Wata",
  yookassa: "YooKassa",
} as const;

/** Display name for a stored provider key; unknown keys come back unchanged. */
export function paymentProviderName(provider: string | null | undefined): string {
  const raw = String(provider || "").trim();
  const key = raw.toLowerCase() as keyof typeof PAYMENT_PROVIDER_NAMES;
  return PAYMENT_PROVIDER_NAMES[key] || raw;
}
