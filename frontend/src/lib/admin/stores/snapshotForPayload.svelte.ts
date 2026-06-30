export function snapshotForPayload<T>(value: T): T {
  return $state.snapshot(value) as T;
}
