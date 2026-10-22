import { publicInformationDocuments, type PublicInformationDocument } from "../informationPages.js";
import { unwrap, type ApiClient } from "../publicApi.js";

export function createPublicDocumentsStore(api: ApiClient["api"]) {
  const state = $state<{ documents: PublicInformationDocument[] | null }>({ documents: null });
  let loaded = false;
  let inFlight: Promise<void> | null = null;

  function load(): Promise<void> {
    if (inFlight) return inFlight;
    if (loaded) return Promise.resolve();

    inFlight = Promise.resolve()
      .then(() => api("/documents"))
      .then((response) => {
        state.documents = publicInformationDocuments(unwrap(response));
        loaded = true;
      })
      .catch(() => {
        // Keep legacy links available, but retry optional content on the next visit.
        state.documents = [];
      })
      .finally(() => {
        inFlight = null;
      });
    return inFlight;
  }

  return {
    get documents() {
      return state.documents;
    },
    load,
  };
}

export type PublicDocumentsStore = ReturnType<typeof createPublicDocumentsStore>;
