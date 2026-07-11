const START_PARAM_KEYS = ["tgWebAppStartParam", "startapp", "start_param"] as const;

export function miniAppPathFromStartParam(value: unknown): string | null {
  const startParam = String(value || "").trim();
  const adminTicket = startParam.match(/^admin_ticket_(\d+)$/i);
  if (adminTicket) return `/admin/support/${adminTicket[1]}`;

  const adminUser = startParam.match(/^admin_user_(-?\d+)$/i);
  if (adminUser) return `/admin/users/${adminUser[1]}`;

  const supportTicket = startParam.match(/^ticket_(\d+)$/i);
  if (supportTicket) return `/support/${supportTicket[1]}`;

  return null;
}

export function miniAppPathFromSearch(search: string): string | null {
  const params = new URLSearchParams(search);
  for (const key of START_PARAM_KEYS) {
    const path = miniAppPathFromStartParam(params.get(key));
    if (path) return path;
  }
  return null;
}
