// SPDX-License-Identifier: AGPL-3.0-or-later
// Which columns the list shows: chosen per collection, kept in this browser.
import type { FieldSchema } from "../api/types";

export const DEFAULT_FIELDS = ["tag", "field_number", "name", "ex", "seeding_date", "last_photo", "last_seen"];

/** Every column the list can show: fields in schema order with the name after the taxonomy, age, photo and visit, custom columns. */
export function allColumns(schema: FieldSchema, custom: string[]): string[] {
  const nameParts = new Set(schema.computed.find((field) => field.key === "name")?.from ?? []);
  const fields = schema.fields.map((field) => field.key);
  const firstPart = fields.findIndex((key) => nameParts.has(key));
  const rest = fields.filter((key) => !nameParts.has(key));
  rest.splice(firstPart < 0 ? rest.length : firstPart, 0, "name");
  return [...rest, "age", "last_photo", "last_seen", ...custom.map((column) => `c:${column}`)];
}

const storageKey = (collection: string) => `squarepot.columns.${collection}`;

export function loadColumns(collection: string, available: string[]): string[] {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(storageKey(collection)) ?? "null");
    if (Array.isArray(saved)) {
      const known = saved.filter((key): key is string => typeof key === "string" && available.includes(key));
      if (known.includes("name")) return known;
    }
  } catch {
    // Unreadable or blocked: the defaults.
  }
  const custom = available.find((key) => key.startsWith("c:"));
  return [...DEFAULT_FIELDS.filter((key) => available.includes(key)), ...(custom ? [custom] : [])];
}

export function saveColumns(collection: string, columns: string[]): void {
  try {
    localStorage.setItem(storageKey(collection), JSON.stringify(columns));
  } catch {
    // Kept for this visit only.
  }
}
