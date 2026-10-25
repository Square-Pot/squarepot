// SPDX-License-Identifier: AGPL-3.0-or-later
// Plant names and other values as schema/fields.yaml says to show them, the same
// way the server prints them on labels (server/src/squarepot_server/labels/caption.py).
import type { Display, FieldSchema } from "../api/types";

export interface Run {
  text: string;
  italic: boolean;
}

export type Fields = Record<string, string>;

export function applyCase(value: string, kind: string | undefined): string {
  switch (kind) {
    case "lower":
      return value.toLowerCase();
    case "upper":
      return value.toUpperCase();
    case "title":
      return value
        .split(" ")
        .map((word) => word.slice(0, 1).toUpperCase() + word.slice(1).toLowerCase())
        .join(" ");
    default:
      return value;
  }
}

/** One value with its prefix, case, italics and quotes. */
export function styled(value: string, display: Display | undefined): Run[] {
  let text = applyCase(value.trim(), display?.case);
  if (display?.quote) text = `‘${text}’`;
  const runs: Run[] = display?.prefix ? [{ text: `${display.prefix} `, italic: false }] : [];
  runs.push({ text, italic: display?.italic ?? false });
  return runs;
}

/** The computed `name`: its `from` fields in order, each styled, empty ones skipped. */
export function nameRuns(schema: FieldSchema, fields: Fields): Run[] {
  const parts = schema.computed.find((field) => field.key === "name")?.from ?? [];
  const runs: Run[] = [];
  for (const key of parts) {
    const value = fields[key]?.trim();
    if (!value) continue;
    if (runs.length) runs.push({ text: " ", italic: false });
    runs.push(...styled(value, displayOf(schema, key)));
  }
  return runs;
}

export function displayOf(schema: FieldSchema, key: string): Display | undefined {
  return schema.fields.find((field) => field.key === key)?.display;
}

export const plainText = (runs: Run[]): string => runs.map((run) => run.text).join("");

/** Whole months from `from` to `now`; `null` when the date is later or unreadable. */
export function monthsSince(from: string, now: Date): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(from);
  if (!match) return null;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  let months = (now.getFullYear() - year) * 12 + (now.getMonth() + 1 - month);
  if (now.getDate() < day) months -= 1;
  return months < 0 ? null : months;
}

/** The computed `age`: since seeding, else since purchase; months under 24, then years. */
export function age(fields: Fields, now: Date): { months: number } | { years: number } | null {
  const from = fields.seeding_date ?? fields.purchase_date;
  if (!from) return null;
  const months = monthsSince(from, now);
  if (months === null) return null;
  return months < 24 ? { months } : { years: Math.floor(months / 12) };
}
