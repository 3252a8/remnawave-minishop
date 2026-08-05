import { describe, expect, it } from "vitest";

import { adminSortState, nextAdminSort, sortAdminRows, type AdminSortColumn } from "./tableSort";

const nameColumn = {
  asc: "name_asc",
  desc: "name_desc",
  defaultDirection: "asc",
  value: (row: { name: string | null }) => row.name,
} satisfies AdminSortColumn<{ name: string | null }>;

describe("admin table sorting", () => {
  it("cycles from the default direction through the opposite direction and off", () => {
    expect(nextAdminSort("", nameColumn)).toBe("name_asc");
    expect(nextAdminSort("name_asc", nameColumn)).toBe("name_desc");
    expect(nextAdminSort("name_desc", nameColumn)).toBe("");
    expect(adminSortState("name_desc", nameColumn)).toBe("descending");
  });

  it("sorts naturally, keeps empty values last, and preserves ties", () => {
    const rows = [
      { id: 1, name: "User 10" },
      { id: 2, name: null },
      { id: 3, name: "user 2" },
      { id: 4, name: "USER 2" },
    ];

    expect(sortAdminRows(rows, "name_asc", [nameColumn]).map((row) => row.id)).toEqual([
      3, 4, 1, 2,
    ]);
    expect(sortAdminRows(rows, "name_desc", [nameColumn]).map((row) => row.id)).toEqual([
      1, 3, 4, 2,
    ]);
  });
});
