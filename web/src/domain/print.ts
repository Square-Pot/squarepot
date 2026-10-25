// SPDX-License-Identifier: AGPL-3.0-or-later
// Printing labels: one label type a sheet, what the labels show, and where they go on the page.
// The geometry mirrors server/src/squarepot_server/labels/layout.py.
import type { components } from "../api/schema";
import type { FieldSchema, LabelTemplate } from "../api/types";
import type { Row } from "./query";

type LabelEntry = components["schemas"]["LabelEntry"];
type Layout = LabelTemplate["layout"];

export type Kind = "vertical" | "horizontal";
export type Order = "list" | "tag";

/** The most plants one request may name. */
export const MAX_PLANTS = 2000;

const PAGE_MM: Record<string, [number, number]> = { a4: [210, 297], letter: [215.9, 279.4] };
const EPSILON = 1e-9;

export function pageSize(layout: Layout): [number, number] {
  return PAGE_MM[layout.page] ?? [210, 297];
}

/** Columns and rows of labels on a page, as the server lays them out. */
export function grid(layout: Layout): { columns: number; rows: number; perPage: number } {
  const [width, height] = pageSize(layout);
  const columns = Math.floor((width - 2 * layout.margin_mm + layout.gap_mm) / (layout.width_mm + layout.gap_mm) + EPSILON);
  const rows = Math.floor((height - 2 * layout.margin_mm + layout.gap_mm) / (layout.height_mm + layout.gap_mm) + EPSILON);
  return { columns, rows, perPage: Math.max(0, columns) * Math.max(0, rows) };
}

/** The position on the page under a point in millimetres, gaps included; `null` outside the labels. */
export function slotAt(layout: Layout, x: number, y: number): number | null {
  const { columns, rows } = grid(layout);
  const column = Math.floor((x - layout.margin_mm) / (layout.width_mm + layout.gap_mm));
  const row = Math.floor((y - layout.margin_mm) / (layout.height_mm + layout.gap_mm));
  if (column < 0 || row < 0 || column >= columns || row >= rows) return null;
  return row * columns + column;
}

/** Places to leave empty, fewer than a page holds: the label type, and with it the page, can change after the choice. */
export const clampSkip = (skip: number, perPage: number): number => Math.max(0, Math.min(skip, perPage - 1));

export const pageCount = (labels: number, skip: number, perPage: number): number =>
  perPage > 0 ? Math.max(1, Math.ceil((skip + labels) / perPage)) : 1;

/** The type a plant asks for in the sheet's `label_type`. */
export const wantedKind = (row: Row): Kind => (row.plant.fields.label_type === "h" ? "horizontal" : "vertical");

/** The type most of the plants ask for; vertical on a tie or with none. */
export function defaultKind(rows: Row[]): Kind {
  const horizontal = rows.filter((row) => wantedKind(row) === "horizontal").length;
  return horizontal * 2 > rows.length ? "horizontal" : "vertical";
}

/** Plants in print order: as the list sorts them, or by label number. */
export function printOrder(rows: Row[], order: Order): Row[] {
  if (order === "list") return rows;
  return [...rows].sort((a, b) => (a.plant.tag ?? "").localeCompare(b.plant.tag ?? "") || a.plant.row - b.plant.row);
}

/** What a label shows, by key: a field key, `name`, or `c:<custom column>`. */
export const toEntries = (keys: string[]): LabelEntry[] =>
  keys.map((key) => (key.startsWith("c:") ? { custom: key.slice(2) } : { field: key }));

/** Fields that can go on a label: the schema's, without the number and the type, which the label has already. */
export function printableFields(schema: FieldSchema): string[] {
  return schema.fields.map((field) => field.key).filter((key) => key !== "tag" && key !== "label_type");
}

export interface LabelFields {
  caption: string[];
  extra: string[];
}

/** The defaults: the «label» preset in the caption, and the burial preset on a label with room for it. */
export function defaultFields(schema: FieldSchema, kind: Kind): LabelFields {
  const preset = (key: string) => schema.presets.find((item) => item.key === key)?.fields ?? [];
  return {
    caption: preset("label").length ? preset("label") : ["name"],
    extra: kind === "horizontal" ? preset("burial") : [],
  };
}

/** Saved fields that still exist, the name first in the caption when it went missing. */
export function cleanFields(saved: unknown, allowed: string[], fallback: LabelFields): LabelFields {
  if (typeof saved !== "object" || saved === null) return fallback;
  const keep = (value: unknown, extra: boolean): string[] | null => {
    if (!Array.isArray(value)) return null;
    const keys = value.filter((key): key is string => typeof key === "string" && allowed.includes(key));
    const unique = [...new Set(keys)].filter((key) => !(extra && key === "name"));
    return unique;
  };
  const caption = keep((saved as Record<string, unknown>).caption, false);
  const extra = keep((saved as Record<string, unknown>).extra, true);
  if (!caption || !extra) return fallback;
  return { caption: caption.includes("name") ? caption : ["name", ...caption], extra };
}
