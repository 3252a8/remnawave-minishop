import { readable, type Readable } from "svelte/store";
import { TableHandler } from "@vincjo/datatables";

type TableHandlerArgs = ConstructorParameters<typeof TableHandler>;
type TableRows = NonNullable<TableHandlerArgs[0]>;
type TableOptions = NonNullable<TableHandlerArgs[1]>;
type RowsTable<T> = object & {
  setRows(rows: T[]): void;
};
type DatatableEventBridge = {
  event?: {
    add?: (event: "change", callback: () => void) => void;
  };
};

const watchedTables = new WeakMap<object, Set<(table: unknown) => void>>();
const watchedTableListeners = new WeakSet<object>();

export function createAdminDatatable(
  rows: TableRows = [],
  options: TableOptions = {}
): TableHandler {
  return new TableHandler(Array.isArray(rows) ? rows : [], options);
}

export function syncAdminDatatable<T>(table: RowsTable<T>, rows: T[] = []): void {
  table.setRows(Array.isArray(rows) ? rows : []);
  notifyAdminDatatable(table);
}

function notifyAdminDatatable(table: object): void {
  const subscribers = watchedTables.get(table);
  if (!subscribers) return;
  for (const set of subscribers) set(table);
}

function ensureAdminDatatableListener(table: object | null | undefined): void {
  if (!table || watchedTableListeners.has(table)) return;
  watchedTableListeners.add(table);
  const eventBridge = table as DatatableEventBridge;
  eventBridge.event?.add?.("change", () => notifyAdminDatatable(table));
}

// The runes-based TableHandler keeps rows, currentPage and pageCount in Svelte 5
// signals that legacy-mode admin components cannot track through a plain const.
// Bridge handler changes into a Svelte store, and notify immediately after
// syncAdminDatatable() so first-load rows render without a user action.
export function watchAdminDatatable<T>(table: T): Readable<T> {
  return readable<T>(table, (set) => {
    if (!table || typeof table !== "object") return;
    const tableObject = table as object;
    ensureAdminDatatableListener(tableObject);
    let subscribers = watchedTables.get(tableObject);
    if (!subscribers) {
      subscribers = new Set();
      watchedTables.set(tableObject, subscribers);
    }
    subscribers.add(set as (table: unknown) => void);
    set(table);
    return () => {
      subscribers.delete(set as (table: unknown) => void);
      if (subscribers.size === 0) watchedTables.delete(tableObject);
    };
  });
}
