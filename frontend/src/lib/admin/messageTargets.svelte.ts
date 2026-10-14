import { unwrap, type ApiClient } from "$lib/webapp/publicApi.js";

export type MessageTarget = { id: string; label: string; owner: string };

export function createMessageTargets(api: ApiClient["api"]) {
  let sections = $state<MessageTarget[]>([]);
  let loading = $state(false);
  let failed = $state(false);

  async function load() {
    if (loading) return;
    loading = true;
    failed = false;
    sections = [];
    try {
      const response = unwrap(await api("/admin/message/targets"));
      sections = (response.sections || [])
        .filter((section) => Boolean(section.owner))
        .map((section) => ({
          id: section.id,
          label: section.label,
          owner: section.owner || "",
        }));
    } catch {
      sections = [];
      failed = true;
    } finally {
      loading = false;
    }
  }
  return {
    get sections() {
      return sections;
    },
    get loading() {
      return loading;
    },
    get failed() {
      return failed;
    },
    load,
  };
}
