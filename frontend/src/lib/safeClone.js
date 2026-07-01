function cloneJsonFallback(value, ancestors = new WeakSet()) {
  if (value === null) return null;

  const valueType = typeof value;
  if (valueType === "string" || valueType === "number" || valueType === "boolean") {
    return value;
  }
  if (valueType === "bigint") return String(value);
  if (valueType !== "object") return undefined;

  if (ancestors.has(value)) return undefined;
  if (value instanceof Date) return value.toISOString();

  ancestors.add(value);

  if (typeof value.toJSON === "function") {
    try {
      const result = cloneJsonFallback(value.toJSON(), ancestors);
      ancestors.delete(value);
      return result;
    } catch (_error) {
      void _error;
    }
  }

  if (Array.isArray(value)) {
    const cloned = value.map((item) => {
      const result = cloneJsonFallback(item, ancestors);
      return result === undefined ? null : result;
    });
    ancestors.delete(value);
    return cloned;
  }

  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    ancestors.delete(value);
    return undefined;
  }

  const cloned = {};
  for (const [key, item] of Object.entries(value)) {
    const result = cloneJsonFallback(item, ancestors);
    if (result !== undefined) cloned[key] = result;
  }
  ancestors.delete(value);
  return cloned;
}

export function structuredCloneSafe(value) {
  if (typeof structuredClone === "function") {
    try {
      return structuredClone(value);
    } catch (_error) {
      void _error;
    }
  }

  try {
    const text = JSON.stringify(value);
    return text === undefined ? undefined : JSON.parse(text);
  } catch (_error) {
    void _error;
  }

  return cloneJsonFallback(value);
}
