type WebappRecord = Record<string, unknown>;

export type InstallGuideEligibilityInput = {
  installGuidesEnabled?: boolean;
  settings?: WebappRecord | null;
  subscription?: WebappRecord | null;
};

export function connectLinkFromSubscription(subscription: WebappRecord | null | undefined) {
  return String(subscription?.connect_url || subscription?.config_link || "").trim();
}

export function canUseSubscriptionInstallGuides({
  installGuidesEnabled,
  settings,
  subscription,
}: InstallGuideEligibilityInput) {
  const enabled =
    typeof installGuidesEnabled === "boolean"
      ? installGuidesEnabled
      : Boolean(settings?.subscription_guides_enabled);
  return Boolean(enabled && subscription?.active);
}

export function trialConnectLink(
  trialActivationResult: WebappRecord | null | undefined,
  subscription: WebappRecord | null | undefined
) {
  return (
    connectLinkFromSubscription(trialActivationResult) || connectLinkFromSubscription(subscription)
  );
}

export function activationConnectLink(
  subscription: WebappRecord | null | undefined,
  trialActivationResult: WebappRecord | null | undefined
) {
  return (
    connectLinkFromSubscription(subscription) || connectLinkFromSubscription(trialActivationResult)
  );
}
