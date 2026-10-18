import type { AdminUser } from "$lib/admin/stores/usersStoreState";
import type { GetResponse } from "$lib/webapp/publicApiContracts";
import type { RelationshipFilter } from "$lib/admin/userRelationships";

type Edge = GetResponse<"/api/admin/users/relationships">["edges"][number];
export function relationshipSubset(users: AdminUser[], edges: Edge[], kind: RelationshipFilter) {
  const visibleEdges = kind === "all" ? edges : edges.filter((edge) => edge.kind === kind);
  const ids = new Set(visibleEdges.flatMap((edge) => [String(edge.source), String(edge.target)]));
  return { users: users.filter((user) => ids.has(String(user.user_id))), edges: visibleEdges, ids };
}
