import { writable, type Writable } from "svelte/store";

import {
  buildMePath,
  createApiClient,
  type ApiClient,
  type MeResponse,
} from "./publicApi";

export type WebappData = MeResponse & Record<string, unknown>;

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

  async function loadData({ fresh = false }: LoadDataOptions = {}): Promise<WebappData> {
    const response = await apiClient.api(buildMePath(fresh));
    const payload = response as WebappData;
    if (payload.ok) data.set(payload);
    return payload;
  }

  return {
    apiClient,
    api: apiClient.api,
    publicApi: apiClient.publicApi,
    data,
    loadData,
  };
}
