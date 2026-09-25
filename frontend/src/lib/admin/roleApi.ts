import { builtApiPath } from "../webapp/publicApi";
import type { AdminApi } from "./stores/usersStoreState";

export type Role = "owner" | "admin";
export type RoleAssignment = {
  user_id: number;
  email: string | null;
  minishop_id: string | null;
  role: Role;
};
export type RoleCandidate = {
  minishop_id: string;
  email: string | null;
  username: string | null;
  first_name: string | null;
};
export type RoleApi = {
  list: () => Promise<RoleAssignment[] | null>;
  candidates: (query: string) => Promise<RoleCandidate[]>;
  grant: (minishopId: string, role: Role) => Promise<void>;
  revoke: (userId: number, role: Role) => Promise<void>;
};

function requireSuccess(response: { ok?: boolean; error?: string } | null | undefined): void {
  if (!response?.ok) throw new Error(response?.error || "role_update_failed");
}

export function createRoleApi(api: AdminApi): RoleApi {
  return {
    async list() {
      const response = await api("/admin/roles");
      return response?.ok && "roles" in response ? (response.roles as RoleAssignment[]) : null;
    },
    async candidates(query) {
      const path = builtApiPath<"/api/admin/roles/candidates">(
        `/admin/roles/candidates?q=${encodeURIComponent(query.trim())}`
      );
      const response = await api(path);
      if (!response?.ok || !("users" in response)) return [];
      return response.users as RoleCandidate[];
    },
    async grant(minishopId, role) {
      requireSuccess(
        await api("/admin/roles", {
          method: "POST",
          body: JSON.stringify({ minishop_id: minishopId, role }),
        })
      );
    },
    async revoke(userId, role) {
      const path = builtApiPath<"/api/admin/roles/{user_id}/{role}">(
        `/admin/roles/${encodeURIComponent(String(userId))}/${role}`
      );
      requireSuccess(await api(path, { method: "DELETE" }));
    },
  };
}
