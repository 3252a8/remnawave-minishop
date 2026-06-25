type WebappRecord = Record<string, unknown>;
type PublicInstallState = WebappRecord & {
  subscription?: WebappRecord | null;
};
type PublicInstallPreload = {
  path?: PublicInstallPath;
  promise?: Promise<WebappRecord | null>;
};
type PublicInstallPath = `/subscription-guides/public/${string}`;
type PublicInstallPreloadHost = Record<string, PublicInstallPreload | null | undefined>;
type PublicInstallGuidesStore = {
  hydrate: (path: PublicInstallPath, payload: WebappRecord) => PublicInstallState;
  loadPublic: (shareToken: string, force?: boolean) => Promise<PublicInstallState>;
  publicPath: (shareToken: string) => PublicInstallPath;
};

export const PUBLIC_INSTALL_PRELOAD_KEY = "__RW_PUBLIC_INSTALL_PRELOAD__";

type PublicInstallActionDeps = {
  getOrigin: () => string;
  getPreloadHost: () => PublicInstallPreloadHost | null;
  installGuidesStore: PublicInstallGuidesStore;
  setActiveTab: (tab: string) => void;
  setMode: (mode: string) => void;
  setPublicInstallSubscription: (subscription: WebappRecord | null) => void;
  setPublicInstallToken: (token: string) => void;
  setScreen: (screen: string) => void;
};

export function publicInstallFallbackSubscription(shareToken: string, origin = ""): WebappRecord {
  return {
    install_share_token: shareToken,
    share_url: origin ? `${origin}/s/${shareToken}` : "",
  };
}

export function createPublicInstallActions({
  getOrigin,
  getPreloadHost,
  installGuidesStore,
  setActiveTab,
  setMode,
  setPublicInstallSubscription,
  setPublicInstallToken,
  setScreen,
}: PublicInstallActionDeps) {
  async function loadPublicInstallGuides(shareToken: string) {
    const path = installGuidesStore.publicPath(shareToken);
    const preloadHost = getPreloadHost();
    const preload = preloadHost?.[PUBLIC_INSTALL_PRELOAD_KEY] || null;
    if (preload?.path === path && preload.promise) {
      const payload = await preload.promise;
      if (payload) {
        if (preloadHost) preloadHost[PUBLIC_INSTALL_PRELOAD_KEY] = null;
        return installGuidesStore.hydrate(path, payload);
      }
    }
    return installGuidesStore.loadPublic(shareToken, true);
  }

  async function loadPublicInstall(shareToken: string) {
    setMode("publicInstall");
    setScreen("install");
    setActiveTab("home");
    setPublicInstallToken(shareToken);
    const fallbackSubscription = publicInstallFallbackSubscription(shareToken, getOrigin());
    setPublicInstallSubscription(fallbackSubscription);
    const response = await loadPublicInstallGuides(shareToken);
    setPublicInstallSubscription(response?.subscription || fallbackSubscription);
  }

  return {
    loadPublicInstall,
    loadPublicInstallGuides,
  };
}
