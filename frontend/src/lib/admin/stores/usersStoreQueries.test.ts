import { describe, expect, it, vi } from "vitest";
import { createUsersStoreQueries } from "./usersStoreQueries";
import type { AdminApi } from "./usersStoreState";

describe("merged user cache invalidation", () => {
  it("invalidates both internal and Minishop detail IDs along with their related data", () => {
    const invalidateQueries = vi.fn(async () => {});
    const api: AdminApi = async () => {
      throw new Error("Cache invalidation must not send an API request");
    };
    const queryClient = {
      invalidateQueries,
      fetchQuery: async <T>({ queryFn }: { queryFn: () => Promise<T> }) => queryFn(),
    };
    const { invalidateUsersQueries } = createUsersStoreQueries({
      api,
      at: (key) => key,
      queryClient,
    });
    invalidateUsersQueries(123);
    invalidateUsersQueries("ms_1234567890abcdef1234567890abcdef");
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["admin", "users", "detail", 123] });
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["admin", "users", "detail", "ms_1234567890abcdef1234567890abcdef"],
    });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["admin", "users", "logs", 123] });
  });
});
