import {
  activationConnectLink,
  connectLinkFromSubscription,
  trialConnectLink,
} from "./connectLinks.js";

type WebappRecord = Record<string, unknown>;

type ConnectActionDeps = {
  getPublicInstallSubscription: () => WebappRecord | null;
  getSubscription: () => WebappRecord | null;
  getTrialActivationResult: () => WebappRecord | null;
  openExternalLink: (url: string) => void;
  showToast: (message: unknown) => void;
  t: (key: string) => unknown;
};

export function createConnectActions({
  getPublicInstallSubscription,
  getSubscription,
  getTrialActivationResult,
  openExternalLink,
  showToast,
  t,
}: ConnectActionDeps) {
  function openResolvedConnectLink(url: string) {
    if (!url) {
      showToast(t("wa_connect_link_unavailable"));
      return false;
    }
    openExternalLink(url);
    return true;
  }

  function openConnectLink() {
    return openResolvedConnectLink(connectLinkFromSubscription(getSubscription()));
  }

  function openPublicConnectLink() {
    return openResolvedConnectLink(connectLinkFromSubscription(getPublicInstallSubscription()));
  }

  function openTrialConnectLink() {
    return openResolvedConnectLink(trialConnectLink(getTrialActivationResult(), getSubscription()));
  }

  function openActivationConnectLink() {
    return openResolvedConnectLink(
      activationConnectLink(getSubscription(), getTrialActivationResult())
    );
  }

  return {
    openActivationConnectLink,
    openConnectLink,
    openPublicConnectLink,
    openResolvedConnectLink,
    openTrialConnectLink,
  };
}
