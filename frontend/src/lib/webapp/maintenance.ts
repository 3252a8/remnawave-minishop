export function isMaintenanceResponse(status: number, payload: unknown): boolean {
  return (
    status === 503 &&
    payload !== null &&
    typeof payload === "object" &&
    "ok" in payload &&
    payload.ok === false &&
    "error" in payload &&
    payload.error === "maintenance_mode"
  );
}

export function isMaintenanceFailure(error: unknown): boolean {
  return (
    error !== null &&
    typeof error === "object" &&
    "status" in error &&
    isMaintenanceResponse(Number(error.status), "payload" in error ? error.payload : error)
  );
}

export function maintenanceFailure(): Error & { status: number; payload: unknown } {
  return Object.assign(new Error("maintenance_mode"), {
    status: 503,
    payload: { ok: false, error: "maintenance_mode" },
  });
}
