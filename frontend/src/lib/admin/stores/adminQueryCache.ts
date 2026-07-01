export const ADMIN_QUERY_STALE_MS = 30 * 1000;

export type AdminQueryKey = readonly unknown[];

export type AdminQueryClient = {
  fetchQuery: <TData>(options: {
    queryKey: AdminQueryKey;
    queryFn: () => Promise<TData>;
    retry: false;
    staleTime: number;
  }) => Promise<TData>;
  invalidateQueries: (options: { queryKey: AdminQueryKey }) => Promise<unknown>;
};

export async function fetchAdminQuery<TData>({
  queryClient,
  queryKey,
  queryFn,
  refresh = false,
  staleTime = ADMIN_QUERY_STALE_MS,
}: {
  queryClient?: AdminQueryClient | null;
  queryKey: AdminQueryKey;
  queryFn: () => Promise<TData>;
  refresh?: boolean;
  staleTime?: number;
}): Promise<TData> {
  if (!queryClient) return queryFn();
  if (refresh) await queryClient.invalidateQueries({ queryKey });
  return queryClient.fetchQuery({
    queryKey,
    queryFn,
    retry: false,
    staleTime,
  });
}

export function invalidateAdminQuery(
  queryClient: AdminQueryClient | null | undefined,
  queryKey: AdminQueryKey
): void {
  if (!queryClient) return;
  void queryClient.invalidateQueries({ queryKey });
}
