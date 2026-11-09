export type Decoder<T> = (value: unknown) => T;
export const text: Decoder<string> = (v) => {
  if (typeof v !== "string")
    throw new Error(
      "Expected text in the API response. Refresh and try again.",
    );
  return v;
};
export const number: Decoder<number> = (v) => {
  if (typeof v !== "number" || !Number.isFinite(v))
    throw new Error(
      "Expected a number in the API response. Refresh and try again.",
    );
  return v;
};
export const boolean: Decoder<boolean> = (v) => {
  if (typeof v !== "boolean")
    throw new Error(
      "Expected a boolean in the API response. Refresh and try again.",
    );
  return v;
};
export const record: Decoder<Record<string, unknown>> = (v) => {
  if (typeof v !== "object" || v === null || Array.isArray(v))
    throw new Error(
      "Expected an object in the API response. Refresh and try again.",
    );
  return Object.fromEntries(Object.entries(v));
};
export const nullable =
  <T>(decode: Decoder<T>): Decoder<T | null> =>
  (v) =>
    v === null ? null : decode(v);
export const optional =
  <T>(decode: Decoder<T>): Decoder<T | undefined> =>
  (v) =>
    v === undefined ? undefined : decode(v);
export const array =
  <T>(decode: Decoder<T>): Decoder<T[]> =>
  (v) => {
    if (!Array.isArray(v))
      throw new Error(
        "Expected a list in the API response. Refresh and try again.",
      );
    return v.map(decode);
  };
export function choice<const T extends string>(...values: T[]): Decoder<T> {
  return (v) => {
    for (const item of values) if (v === item) return item;
    throw new Error("An API value was not recognised. Refresh and try again.");
  };
}
export function shape<S extends Record<string, Decoder<unknown>>>(
  fields: S,
): Decoder<{ [K in keyof S]: ReturnType<S[K]> }> {
  return (value) => {
    const input = record(value);
    const output: Record<string, unknown> = {};
    for (const [key, decode] of Object.entries(fields))
      output[key] = decode(input[key]);
    // Every declared property was validated by its decoder above.
    return output as { [K in keyof S]: ReturnType<S[K]> };
  };
}
export function parseFilter(value: string): Record<string, unknown> | null {
  return value.trim() ? record(JSON.parse(value)) : null;
}
