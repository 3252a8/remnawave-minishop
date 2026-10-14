import type { AdminUser } from "./stores/usersStoreState.js";

type UserPage = { users: AdminUser[]; total: number; page?: number; page_size?: number };

/** Independent list state keeps a dialog's search out of the main users table. */
export function createUserPicker(loadPage: (query: string, page: number) => Promise<UserPage>) {
  let query = $state("");
  let users = $state<AdminUser[]>([]);
  let total = $state<number | null>(null);
  let page = $state(0);
  let pageSize = $state(25);
  let loading = $state(false);
  let failed = $state(false);
  let dirty = $state(false);
  let generation = 0;

  function changeQuery(value: string) {
    generation += 1;
    query = value;
    users = [];
    total = null;
    page = 0;
    loading = false;
    failed = false;
    dirty = true;
  }

  async function load(nextPage = 0) {
    const current = ++generation;
    const currentQuery = query.trim();
    page = nextPage;
    users = [];
    total = null;
    loading = true;
    failed = false;
    dirty = false;
    try {
      const response = await loadPage(currentQuery, nextPage);
      if (current !== generation) return;
      users = response.users;
      total = response.total;
      page = response.page ?? nextPage;
      pageSize = response.page_size || 25;
    } catch {
      if (current === generation) failed = true;
    } finally {
      if (current === generation) loading = false;
    }
  }

  return {
    get query() {
      return query;
    },
    get users() {
      return users;
    },
    get total() {
      return total;
    },
    get page() {
      return page;
    },
    get pageCount() {
      return Math.max(1, Math.ceil((total ?? 0) / pageSize));
    },
    get loading() {
      return loading;
    },
    get failed() {
      return failed;
    },
    get dirty() {
      return dirty;
    },
    changeQuery,
    load,
    dispose() {
      generation += 1;
    },
  };
}
