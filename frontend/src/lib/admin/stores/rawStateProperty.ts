export function defineRawStateProperty<TStore extends object, TKey extends keyof TStore>(
  store: TStore,
  key: TKey,
  accessors: {
    get: () => TStore[TKey];
    set: (value: TStore[TKey]) => void;
  }
): void {
  Object.defineProperty(store, key, {
    configurable: true,
    enumerable: true,
    get: accessors.get,
    set: accessors.set,
  });
}
