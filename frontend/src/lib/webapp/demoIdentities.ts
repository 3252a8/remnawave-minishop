/** Stable, UUID-shaped public identities for the anonymized demo snapshot. */
export function demoMinishopId(userId: unknown, existing?: unknown): string | null {
  if (typeof existing === "string" && /^ms_[0-9a-f]{32}$/i.test(existing)) return existing;
  const id = Number(userId);
  if (!Number.isSafeInteger(id) || id === 0) return null;
  const namespace = id < 0 ? "2000000000004000800" : "1000000000004000800";
  return `ms_${namespace}${Math.abs(id).toString(16).padStart(13, "0")}`;
}

/** Decorate the snapshot at its consumption boundary; never edit generated data. */
export function withDemoIdentities<T>(value: T): T {
  if (Array.isArray(value)) return value.map(withDemoIdentities) as T;
  if (!value || typeof value !== "object") return value;
  const record: Record<string, unknown> = Object.fromEntries(
    Object.entries(value).map(([key, item]) => [key, withDemoIdentities(item)])
  );
  if (record.user_id) {
    record.minishop_id = demoMinishopId(record.user_id, record.minishop_id);
    record.user_minishop_id = record.minishop_id;
  }
  for (const prefix of ["target_user", "actor_user", "purchaser", "recipient"]) {
    const id = record[`${prefix}_id`] ?? record[`${prefix}_user_id`];
    if (id) record[`${prefix}_minishop_id`] = demoMinishopId(id, record[`${prefix}_minishop_id`]);
  }
  return record as T;
}
