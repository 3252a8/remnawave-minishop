export type ReferralLinkEntry = {
  id: "webapp" | "telegram";
  labelKey: "wa_referral_webapp_link_label" | "wa_referral_telegram_link_label";
  url: string;
};

type ReferralLinkSource = {
  bot_link?: unknown;
  webapp_link?: unknown;
};

export function visibleReferralLinks(referral: ReferralLinkSource): ReferralLinkEntry[] {
  const webappUrl = String(referral?.webapp_link || "").trim();
  const telegramUrl = String(referral?.bot_link || "").trim();
  return [
    ...(webappUrl
      ? [{ id: "webapp", labelKey: "wa_referral_webapp_link_label", url: webappUrl } as const]
      : []),
    ...(telegramUrl
      ? [
          {
            id: "telegram",
            labelKey: "wa_referral_telegram_link_label",
            url: telegramUrl,
          } as const,
        ]
      : []),
  ];
}
