export type AdminSortState = "none" | "ascending" | "descending";
export type AdminSortDirection = "asc" | "desc";
export type AdminSortValue = string | number | boolean | Date | null | undefined;

export type AdminSortSpec = {
  asc: string;
  desc: string;
  defaultDirection: AdminSortDirection;
};

export type AdminSortColumn<Row = never> = AdminSortSpec & {
  value?: (row: Row) => AdminSortValue | readonly AdminSortValue[];
};

type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

const collator = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: "base",
});

export function adminSortState(currentSort: string, column: AdminSortSpec): AdminSortState {
  if (currentSort === column.asc) return "ascending";
  if (currentSort === column.desc) return "descending";
  return "none";
}

export function nextAdminSort(currentSort: string, column: AdminSortSpec): string {
  const state = adminSortState(currentSort, column);
  const defaultValue = column[column.defaultDirection];
  if (state === "none") return defaultValue;
  if (currentSort === defaultValue) {
    return column.defaultDirection === "asc" ? column.desc : column.asc;
  }
  return "";
}

export function adminSortTitle(state: AdminSortState, at: TranslateFn): string {
  if (state === "ascending") return at("sort_ascending", {}, "Sorted ascending");
  if (state === "descending") return at("sort_descending", {}, "Sorted descending");
  return at("sort_off", {}, "Not sorted");
}

function compareScalar(left: AdminSortValue, right: AdminSortValue, direction: number): number {
  const leftEmpty = left == null || left === "";
  const rightEmpty = right == null || right === "";
  if (leftEmpty || rightEmpty) {
    if (leftEmpty && rightEmpty) return 0;
    return leftEmpty ? 1 : -1;
  }
  if (left instanceof Date || right instanceof Date) {
    const leftTime = Number(left instanceof Date ? left : new Date(String(left)));
    const rightTime = Number(right instanceof Date ? right : new Date(String(right)));
    if (Number.isFinite(leftTime) && Number.isFinite(rightTime)) {
      return (leftTime - rightTime) * direction;
    }
  }
  if (typeof left === "number" && typeof right === "number") return (left - right) * direction;
  if (typeof left === "boolean" && typeof right === "boolean") {
    return (Number(left) - Number(right)) * direction;
  }
  return collator.compare(String(left), String(right)) * direction;
}

function compareValues(
  left: AdminSortValue | readonly AdminSortValue[],
  right: AdminSortValue | readonly AdminSortValue[],
  direction: number
): number {
  const leftValues = Array.isArray(left) ? left : [left];
  const rightValues = Array.isArray(right) ? right : [right];
  const count = Math.max(leftValues.length, rightValues.length);
  for (let index = 0; index < count; index += 1) {
    const result = compareScalar(leftValues[index], rightValues[index], direction);
    if (result) return result;
  }
  return 0;
}

export function sortAdminRows<Row>(
  rows: readonly Row[],
  currentSort: string,
  columns: readonly AdminSortColumn<Row>[]
): Row[] {
  const column = columns.find(
    (candidate) => currentSort === candidate.asc || currentSort === candidate.desc
  );
  if (!column?.value) return [...rows];
  const direction = currentSort === column.desc ? -1 : 1;
  return rows
    .map((row, index) => ({ row, index }))
    .sort((left, right) => {
      const result = compareValues(column.value!(left.row), column.value!(right.row), direction);
      return result || left.index - right.index;
    })
    .map(({ row }) => row);
}
