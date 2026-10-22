import { DATASET } from "./dataset";
import { demoPartnerRelationships } from "./partnerProgram";
import { withDemoAvatars } from "./users";

export function demoUserRelationships() {
  const scenario = new URLSearchParams(window.location.search).get("relationships_scenario");
  if (scenario === "empty") {
    return { ok: true, nodes: [], edges: [] };
  }
  const users = DATASET.adminUsers || [];
  const ids = new Set(users.map((user) => Number(user.user_id)));
  const referralEdges = users.flatMap((user) => {
    const source = Number(user.referred_by_id);
    const target = Number(user.user_id);
    return source !== target && ids.has(source)
      ? [{ source, target, kind: "referral" as const }]
      : [];
  });
  const edges = [...referralEdges, ...demoPartnerRelationships()];
  const connected = new Set(edges.flatMap((edge) => [edge.source, edge.target]));
  return {
    ok: true,
    nodes: withDemoAvatars(users.filter((user) => connected.has(Number(user.user_id)))).map(
      (user) =>
        scenario === "long-identity" && Number(user.user_id) === 910001
          ? {
              ...user,
              first_name: "Alexandra Roždestvenskaya",
              last_name: "Partner Operations and Community Support",
              username: "alexandra_rozhdestvenskaya_support",
              email: "alexandra.rozhdestvenskaya+partner.operations@very-long-domain.example.com",
            }
          : user
    ),
    edges,
  };
}
