// SPDX-License-Identifier: AGPL-3.0-or-later
// The list: search, filters with counts, sorting, and their place in the URL.
// Everything runs over the local copy of the collection; the API has no search.
import type { FieldSchema, Plant } from "../api/types";
import { age, applyCase, displayOf, nameRuns, plainText, type Run } from "./names";

export type Tagged = "all" | "yes" | "no";
/** Photos: any, none at all, or the newest one older than `photoAge` months. */
export type PhotoFilter = "any" | "none" | "old";
/** Visits: any, not seen since `since` (never seen too), or never seen. */
export type SeenFilter = "any" | "since" | "never";
/** Former plants, those with a status: left out, shown too, or shown alone. */
export type FormerFilter = "hide" | "show" | "only";

export const PHOTO_AGES = [6, 12, 24];

export interface Sort {
  /** `name`, `age`, a field key, or `c:<custom column>`. */
  key: string;
  desc: boolean;
}

export interface ListState {
  q: string;
  sort: Sort;
  genus: string[];
  tagged: Tagged;
  /** Chosen values by custom column; `""` stands for an empty cell. */
  custom: Record<string, string[]>;
  photo: PhotoFilter;
  photoAge: number;
  seen: SeenFilter;
  /** `YYYY-MM-DD`, for `seen: "since"`. */
  since: string;
  former: FormerFilter;
}

export const DEFAULT_SORT: Sort = { key: "name", desc: false };
export const EMPTY_STATE: ListState = {
  q: "",
  sort: DEFAULT_SORT,
  genus: [],
  tagged: "all",
  custom: {},
  photo: "any",
  photoAge: 12,
  seen: "any",
  since: "",
  former: "hide",
};
const CUSTOM_PREFIX = "c.";

export function parseListState(params: URLSearchParams): ListState {
  const sort = params.get("sort") ?? "";
  const tag = params.get("tag");
  // A Map, then own properties: a column may be named anything, `__proto__` too.
  const chosen = new Map<string, string[]>();
  for (const [key, value] of params) {
    if (!key.startsWith(CUSTOM_PREFIX) || key.length === CUSTOM_PREFIX.length) continue;
    const column = key.slice(CUSTOM_PREFIX.length);
    chosen.set(column, [...(chosen.get(column) ?? []), value]);
  }
  const custom = Object.fromEntries(chosen);
  const photo = params.get("photo");
  const photoAge = Number(params.get("photo_age"));
  const since = params.get("since") ?? "";
  const former = params.get("former");
  const validSince = /^\d{4}-\d{2}-\d{2}$/.test(since);
  return {
    q: params.get("q") ?? "",
    sort: sort
      ? { key: sort.replace(/^-/, ""), desc: sort.startsWith("-") }
      : DEFAULT_SORT,
    genus: params.getAll("genus"),
    tagged: tag === "yes" || tag === "no" ? tag : "all",
    custom,
    photo: photo === "none" || photo === "old" ? photo : "any",
    photoAge: PHOTO_AGES.includes(photoAge) ? photoAge : EMPTY_STATE.photoAge,
    seen: params.get("seen") === "never" ? "never" : validSince ? "since" : "any",
    since: validSince ? since : "",
    former: former === "show" || former === "only" ? former : "hide",
  };
}

/** The state as a query string, leaving out what is default. */
export function serializeListState(state: ListState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.sort.key !== DEFAULT_SORT.key || state.sort.desc !== DEFAULT_SORT.desc) {
    params.set("sort", (state.sort.desc ? "-" : "") + state.sort.key);
  }
  for (const genus of state.genus) params.append("genus", genus);
  if (state.tagged !== "all") params.set("tag", state.tagged);
  for (const [column, values] of Object.entries(state.custom)) {
    for (const value of values) params.append(CUSTOM_PREFIX + column, value);
  }
  if (state.photo !== "any") params.set("photo", state.photo);
  if (state.photo === "old" && state.photoAge !== EMPTY_STATE.photoAge) params.set("photo_age", String(state.photoAge));
  if (state.seen === "never") params.set("seen", "never");
  else if (state.seen === "since" && state.since) params.set("since", state.since);
  if (state.former !== "hide") params.set("former", state.former);
  return params;
}

export const filterCount = (state: ListState): number =>
  state.genus.length +
  (state.tagged === "all" ? 0 : 1) +
  Object.values(state.custom).reduce((sum, values) => sum + values.length, 0) +
  (state.photo === "any" ? 0 : 1) +
  (state.seen === "any" ? 0 : 1) +
  (state.former === "hide" ? 0 : 1);

/** The state with every filter cleared, the search and sort kept. */
export const clearFilters = (state: ListState): ListState => ({ ...EMPTY_STATE, q: state.q, sort: state.sort });

/** A plant with what the list needs worked out once. */
export interface Row {
  plant: Plant;
  name: Run[];
  nameText: string;
  genus: string;
}

export function makeRows(schema: FieldSchema, plants: Plant[]): Row[] {
  const genusCase = displayOf(schema, "genus")?.case;
  return plants.map((plant) => {
    const name = nameRuns(schema, plant.fields);
    return {
      plant,
      name,
      nameText: plainText(name),
      genus: applyCase(plant.fields.genus?.trim() ?? "", genusCase),
    };
  });
}

const compact = (value: string): string => value.toLowerCase().replace(/\s+/g, "");
const isNumber = (value: string): boolean => /^\d+$/.test(value);

/** A label number with or without its zeros, a field number with or without spaces, or part of the name. */
export function matchesQuery(row: Row, q: string): boolean {
  const query = q.trim();
  if (!query) return true;
  const short = compact(query);
  const tag = row.plant.tag;
  // Zeros or not, the typed digits are part of the six-digit number.
  if (isNumber(short) && tag?.includes(short)) return true;
  const fieldNumber = row.plant.fields.field_number;
  if (fieldNumber && compact(fieldNumber).includes(short)) return true;
  return row.nameText.toLowerCase().includes(query.toLowerCase());
}

/** A filter group: values inside one are OR-ed, groups are AND-ed. */
export type Group = "genus" | "tagged" | "photo" | "seen" | "former" | `c:${string}`;

/** A record's own value: a column named like a built-in property, `__proto__` or `constructor`, is just a column. */
export const own = <T>(record: Record<string, T>, key: string): T | undefined =>
  Object.hasOwn(record, key) ? record[key] : undefined;

const customValue = (row: Row, column: string): string => own(row.plant.custom, column)?.trim() ?? "";

export const isFormer = (row: Row): boolean => !!row.plant.fields.status;

/** A former plant is still found by its whole number, as the camera finds it. */
function foundByNumber(row: Row, q: string): boolean {
  const short = compact(q);
  return isNumber(short) && !!row.plant.tag && Number(short) === Number(row.plant.tag);
}

/** The start of a local day `YYYY-MM-DD`, in ms. */
const dayStart = (day: string): number => new Date(`${day}T00:00:00`).getTime();

/** The same moment `months` earlier. */
function monthsBefore(now: Date, months: number): number {
  const date = new Date(now);
  date.setMonth(date.getMonth() - months);
  return date.getTime();
}

function passes(row: Row, state: ListState, now: Date, skip?: Group): boolean {
  if (!matchesQuery(row, state.q)) return false;
  const { plant } = row;
  if (skip !== "former") {
    if (state.former === "hide" && isFormer(row) && !foundByNumber(row, state.q)) return false;
    if (state.former === "only" && !isFormer(row)) return false;
  }
  if (skip !== "photo") {
    if (state.photo === "none" && plant.photo_count > 0) return false;
    if (state.photo === "old" && (!plant.last_photo || Date.parse(plant.last_photo) >= monthsBefore(now, state.photoAge))) {
      return false;
    }
  }
  if (skip !== "seen") {
    if (state.seen === "never" && plant.last_seen) return false;
    if (state.seen === "since" && state.since && plant.last_seen && Date.parse(plant.last_seen) >= dayStart(state.since)) {
      return false;
    }
  }
  if (skip !== "genus" && state.genus.length && !state.genus.includes(row.genus)) return false;
  if (skip !== "tagged" && state.tagged !== "all" && (state.tagged === "yes") !== !!row.plant.tag) {
    return false;
  }
  for (const [column, values] of Object.entries(state.custom)) {
    if (skip === `c:${column}` || !values.length) continue;
    if (!values.includes(customValue(row, column))) return false;
  }
  return true;
}

export const filterRows = (rows: Row[], state: ListState, now: Date): Row[] =>
  rows.filter((row) => passes(row, state, now));

export interface FacetValue {
  value: string;
  count: number;
}

export interface Facets {
  genus: FacetValue[];
  tagged: { yes: number; no: number };
  custom: { column: string; values: FacetValue[] }[];
  /** How many rows each choice would give, under the other groups' filters. */
  photo: Record<PhotoFilter, number>;
  seen: Record<SeenFilter, number>;
  former: Record<FormerFilter, number>;
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

/** Every value of every group, each counted under the other groups' filters. */
export function facets(rows: Row[], state: ListState, columns: string[], now: Date): Facets {
  const count = (group: Group, valueOf: (row: Row) => string): FacetValue[] => {
    const counts = new Map<string, number>();
    for (const row of rows) counts.set(valueOf(row), counts.get(valueOf(row)) ?? 0);
    for (const row of rows) {
      if (passes(row, state, now, group)) {
        const value = valueOf(row);
        counts.set(value, (counts.get(value) ?? 0) + 1);
      }
    }
    return [...counts]
      .map(([value, n]) => ({ value, count: n }))
      .sort((a, b) => (a.value === "" ? 1 : b.value === "" ? -1 : collator.compare(a.value, b.value)));
  };
  const tagged = { yes: 0, no: 0 };
  for (const row of rows) {
    if (passes(row, state, now, "tagged")) tagged[row.plant.tag ? "yes" : "no"] += 1;
  }
  const choices = <K extends string>(options: Record<K, Partial<ListState>>): Record<K, number> => {
    const out = {} as Record<K, number>;
    for (const key of Object.keys(options) as K[]) {
      const chosen = { ...state, ...options[key] };
      out[key] = rows.filter((row) => passes(row, chosen, now)).length;
    }
    return out;
  };
  return {
    genus: count("genus", (row) => row.genus).filter((facet) => facet.value !== ""),
    tagged,
    custom: columns.map((column) => ({
      column,
      values: count(`c:${column}`, (row) => customValue(row, column)),
    })),
    photo: choices({ any: { photo: "any" }, none: { photo: "none" }, old: { photo: "old" } }),
    seen: choices({ any: { seen: "any" }, since: { seen: "since" }, never: { seen: "never" } }),
    former: choices({ hide: { former: "hide" }, show: { former: "show" }, only: { former: "only" } }),
  };
}

type SortValue = string | number | null;

function sortValue(schema: FieldSchema, row: Row, key: string, now: Date): SortValue {
  if (key === "name") return row.nameText;
  if (key === "tag") return row.plant.tag;
  if (key === "last_photo") return row.plant.last_photo;
  if (key === "last_seen") return row.plant.last_seen;
  if (key === "age") {
    const value = age(row.plant.fields, now);
    if (!value) return null;
    return "months" in value ? value.months : value.years * 12;
  }
  if (key.startsWith("c:")) return customValue(row, key.slice(2)) || null;
  const value = row.plant.fields[key];
  if (value === undefined) return null;
  const type = schema.fields.find((field) => field.key === key)?.type;
  return type === "decimal" ? Number(value) : value;
}

/** Sorted by `sort`, empty values last either way, then by sheet row. */
export function sortRows(schema: FieldSchema, rows: Row[], sort: Sort, now: Date): Row[] {
  const keyed = rows.map((row) => ({ row, value: sortValue(schema, row, sort.key, now) }));
  keyed.sort((a, b) => {
    if (a.value === null || b.value === null) {
      if (a.value !== b.value) return a.value === null ? 1 : -1;
    } else {
      const order =
        typeof a.value === "number" && typeof b.value === "number"
          ? a.value - b.value
          : collator.compare(String(a.value), String(b.value));
      if (order) return sort.desc ? -order : order;
    }
    return a.row.plant.row - b.row.plant.row;
  });
  return keyed.map((item) => item.row);
}

export interface Piece {
  text: string;
  mark: boolean;
}

/** `text` split around the first case-blind match of `query`. */
export function highlight(text: string, query: string): Piece[] {
  const q = query.trim().toLowerCase();
  const at = q ? text.toLowerCase().indexOf(q) : -1;
  if (at < 0) return [{ text, mark: false }];
  return [
    { text: text.slice(0, at), mark: false },
    { text: text.slice(at, at + q.length), mark: true },
    { text: text.slice(at + q.length), mark: false },
  ].filter((piece) => piece.text);
}

/** A name's runs split around a match of `query` in its plain text, keeping each run's italics. */
export function highlightRuns(runs: Run[], query: string): (Run & { mark: boolean })[] {
  const q = query.trim().toLowerCase();
  const text = plainText(runs).toLowerCase();
  const start = q && !isNumber(compact(q)) ? text.indexOf(q) : -1;
  const end = start + q.length;
  const out: (Run & { mark: boolean })[] = [];
  let pos = 0;
  for (const run of runs) {
    const from = pos;
    const to = pos + run.text.length;
    pos = to;
    if (start < 0 || end <= from || start >= to) {
      out.push({ ...run, mark: false });
      continue;
    }
    const a = Math.max(start, from) - from;
    const b = Math.min(end, to) - from;
    if (a > 0) out.push({ text: run.text.slice(0, a), italic: run.italic, mark: false });
    out.push({ text: run.text.slice(a, b), italic: run.italic, mark: true });
    if (b < run.text.length) out.push({ text: run.text.slice(b), italic: run.italic, mark: false });
  }
  return out;
}

/** The part of a label number that a numeric query matched. */
export function tagMatch(tag: string, query: string): string {
  const short = compact(query);
  return isNumber(short) && tag.includes(short) ? short : "";
}

/** Whether a field number matches the query, spaces ignored. */
export const fieldNumberMatches = (value: string, query: string): boolean =>
  !!query.trim() && compact(value).includes(compact(query));
