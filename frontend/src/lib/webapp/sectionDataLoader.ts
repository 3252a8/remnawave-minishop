type WebappRecord = Record<string, unknown>;

type SectionDataDevicesStore = {
  loadDevices: (devicesEnabled: boolean, force?: boolean) => unknown;
};

type SectionDataInstallGuidesStore = {
  load: (force?: boolean) => unknown;
};

type SectionDataSupportStore = {
  loadList: (options?: WebappRecord) => unknown;
  openTicket: (ticketId: number | string, opts?: WebappRecord) => unknown;
  startPolling: (options?: WebappRecord) => unknown;
};

export type SectionDataLoaderDeps = {
  devicesStore: SectionDataDevicesStore;
  installGuidesStore: SectionDataInstallGuidesStore;
  supportStore: SectionDataSupportStore;
};

export type LoadSectionDataInput = {
  initialSupportTicketId: number | null;
  installGuidesPromise: unknown;
  payload: WebappRecord;
  section: string;
};

function recordField(value: unknown): WebappRecord {
  return value && typeof value === "object" ? (value as WebappRecord) : {};
}

/**
 * Applies the section-specific data preload that runs after `/me` resolves and the route has
 * settled. Mirrors the original `loadData` ordering exactly: devices is awaited, then install
 * guides, then the support ticket/list — divergent sections still kick a background install-guide
 * load when guides are available for the active subscription.
 */
export function createSectionDataLoader({
  devicesStore,
  installGuidesStore,
  supportStore,
}: SectionDataLoaderDeps) {
  async function loadSectionData({
    initialSupportTicketId,
    installGuidesPromise,
    payload,
    section,
  }: LoadSectionDataInput): Promise<void> {
    const settings = recordField(payload.settings);
    const subscription = recordField(payload.subscription);

    if (section === "devices" && settings.my_devices_enabled) {
      await devicesStore.loadDevices(true, true);
    }
    if (section === "install") {
      await (installGuidesPromise || installGuidesStore.load());
    } else if (settings.subscription_guides_enabled && subscription.active) {
      void installGuidesStore.load();
    }
    if (section === "support") {
      if (initialSupportTicketId) {
        await supportStore.openTicket(initialSupportTicketId, { skipPush: true });
      } else {
        await supportStore.loadList();
      }
      supportStore.startPolling({ includeList: true });
    }
  }

  return { loadSectionData };
}
