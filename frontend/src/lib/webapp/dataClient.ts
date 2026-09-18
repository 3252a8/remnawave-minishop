import { writable, type Writable } from "svelte/store";

import type { WebappData } from "./domainTypes";
import { buildMePath, createApiClient, type ApiClient } from "./publicApi";

export type LoadDataOptions = {
  fresh?: boolean;
};

export type WebappDataClient = {
  apiClient: ApiClient;
  api: ApiClient["api"];
  publicApi: ApiClient["publicApi"];
  data: Writable<WebappData | null>;
  loadData(options?: LoadDataOptions): Promise<WebappData>;
};

export function createWebappDataClient(
  options: Parameters<typeof createApiClient>[0] = {},
  initialData: WebappData | null = null
): WebappDataClient {
  const apiClient = createApiClient(options);
  const data = writable<WebappData | null>(initialData);
  let flight: { fresh: boolean; promise: Promise<WebappData> } | null = null;
  let generation = 0;
  let latestPayload = initialData;
  let latestSuccessfulGeneration = 0;

  async function loadData({ fresh = false }: LoadDataOptions = {}): Promise<WebappData> {
    if (flight && (flight.fresh || !fresh)) return flight.promise;
    const ownGeneration = ++generation;
    const promise = (async () => {
      const response = await apiClient.api(buildMePath(fresh));
      if (ownGeneration !== generation) {
        if (flight) return flight.promise;
        if (latestPayload && latestSuccessfulGeneration === generation) return latestPayload;
        throw new DOMException("superseded_profile", "AbortError");
      }
      const payload = response as WebappData;
      if (payload.ok) {
        latestPayload = payload;
        latestSuccessfulGeneration = ownGeneration;
        data.set(payload);
      }
      return payload;
    })();
    flight = { fresh, promise };
    try {
      return await promise;
    } finally {
      if (flight?.promise === promise) flight = null;
    }
  }

  return {
    apiClient,
    api: apiClient.api,
    publicApi: apiClient.publicApi,
    data,
    loadData,
  };
}
