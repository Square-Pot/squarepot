// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";
import type { Plant } from "../api/types";
import { plant, SCHEMA } from "./fixtures";
import {
  clearFilters,
  EMPTY_STATE,
  facets,
  filterRows,
  highlightRuns,
  makeRows,
  matchesQuery,
  own,
  parseListState,
  serializeListState,
  sortRows,
  tagMatch,
  type ListState,
} from "./query";

const ROWS = makeRows(SCHEMA, [
  plant(2, "002187", { genus: "Lithops", species: "lesliei", field_number: "PV 2187A" }, {
    Marathon: "Конкурсный 2023",
  }),
  plant(3, "000012", { genus: "lithops", species: "aucampiae", price: "12.50" }, { Marathon: "Резерв" }),
  plant(4, null, { genus: "Conophytum", species: "bilobum", price: "7.50" }),
  plant(5, "000100", { genus: "Conophytum", species: "minimum", seeding_date: "2020-01-01" }, {
    Marathon: "Конкурсный 2023",
  }),
]);
const NOW = new Date(2026, 9, 26, 12);
const state = (change: Partial<ListState>): ListState => ({ ...EMPTY_STATE, ...change });
const rows = (list: typeof ROWS) => list.map((row) => row.plant.row);

describe("search", () => {
  it.each([
    ["2187", [2]],
    ["002187", [2]],
    ["12", [3]],
    ["21", [2]],
    ["pv2187a", [2]],
    ["PV 2187", [2]],
    ["ops les", [2]],
    ["CONO", [4, 5]],
    ["  ", [2, 3, 4, 5]],
  ])("%s finds rows %j", (q, expected) => {
    expect(rows(ROWS.filter((row) => matchesQuery(row, q)))).toEqual(expected);
  });

  it("marks the match inside a name across its parts", () => {
    const [first] = ROWS;
    const marked = highlightRuns(first?.name ?? [], "ops les");
    expect(marked.filter((run) => run.mark).map((run) => run.text)).toEqual(["ops", " ", "les"]);
    expect(highlightRuns(first?.name ?? [], "2187").some((run) => run.mark)).toBe(false);
  });

  it("marks the matched part of a label number", () => {
    expect(tagMatch("002187", "2187")).toBe("2187");
    expect(tagMatch("000012", "012")).toBe("012");
    expect(tagMatch("000012", "0000012")).toBe("");
    expect(tagMatch("000012", "lith")).toBe("");
  });
});

describe("filters", () => {
  it("are OR inside a group and AND between groups", () => {
    expect(rows(filterRows(ROWS, state({ genus: ["Lithops", "Conophytum"] }), NOW))).toEqual([2, 3, 4, 5]);
    expect(
      rows(filterRows(ROWS, state({ genus: ["Conophytum"], custom: { Marathon: ["Конкурсный 2023"] } }), NOW)),
    ).toEqual([5]);
    expect(rows(filterRows(ROWS, state({ custom: { Marathon: [""] } }), NOW))).toEqual([4]);
    expect(rows(filterRows(ROWS, state({ tagged: "no" }), NOW))).toEqual([4]);
  });

  it("count each value under the other groups, listing values with none", () => {
    const result = facets(ROWS, state({ genus: ["Lithops"] }), ["Marathon"], NOW);
    // The genus group ignores its own choice; genus is merged by its display case.
    expect(result.genus).toEqual([
      { value: "Conophytum", count: 2 },
      { value: "Lithops", count: 2 },
    ]);
    expect(result.tagged).toEqual({ yes: 2, no: 0 });
    expect(result.custom[0]?.values).toEqual([
      { value: "Конкурсный 2023", count: 1 },
      { value: "Резерв", count: 1 },
      { value: "", count: 0 },
    ]);
  });
});

describe("inventory filters", () => {
  const seen = (row: number, tag: string | null, change: Partial<Plant>, fields: Record<string, string> = {}) => ({
    ...plant(row, tag, { genus: "Lithops", ...fields }),
    ...change,
  });
  const INVENTORY = makeRows(SCHEMA, [
    seen(2, "000002", {}),
    seen(3, "000003", { photo_count: 2, last_photo: "2026-10-01T10:00:00Z", last_seen: "2026-10-01T10:00:00Z" }),
    seen(4, "000004", { photo_count: 1, last_photo: "2025-05-01T10:00:00Z", last_seen: "2026-09-01T10:00:00Z" }),
    seen(5, "000005", { last_seen: "2026-10-20T10:00:00Z" }),
    seen(6, "000006", {}, { status: "dead" }),
  ]);
  const found = (change: Partial<ListState>) => rows(filterRows(INVENTORY, state(change), NOW));

  it("leave former plants out unless asked, but find them by their whole number", () => {
    expect(found({})).toEqual([2, 3, 4, 5]);
    expect(found({ former: "show" })).toEqual([2, 3, 4, 5, 6]);
    expect(found({ former: "only" })).toEqual([6]);
    expect(found({ q: "6" })).toEqual([6]);
    expect(found({ q: "000006" })).toEqual([6]);
  });

  it("pick plants with no photo, or an old one", () => {
    expect(found({ photo: "none" })).toEqual([2, 5]);
    expect(found({ photo: "old" })).toEqual([4]);
    expect(found({ photo: "old", photoAge: 24 })).toEqual([]);
  });

  it("pick plants not seen since a day, never seen ones too, or never seen", () => {
    expect(found({ seen: "since", since: "2026-10-01" })).toEqual([2, 4]);
    expect(found({ seen: "since", since: "2026-10-02" })).toEqual([2, 3, 4]);
    expect(found({ seen: "never" })).toEqual([2]);
  });

  it("count each choice under the other filters", () => {
    const result = facets(INVENTORY, state({ photo: "none" }), [], NOW);
    expect(result.photo).toEqual({ any: 4, none: 2, old: 1 });
    expect(result.seen).toEqual({ any: 2, since: 2, never: 1 });
    expect(result.former).toEqual({ hide: 2, show: 3, only: 1 });
    expect(result.tagged).toEqual({ yes: 2, no: 0 });
  });

  it("sort by the last photo and the last visit, never last", () => {
    expect(rows(sortRows(SCHEMA, INVENTORY, { key: "last_photo", desc: false }, NOW))).toEqual([4, 3, 2, 5, 6]);
    expect(rows(sortRows(SCHEMA, INVENTORY, { key: "last_seen", desc: true }, NOW))).toEqual([5, 3, 4, 2, 6]);
  });

  it("are counted, cleared, and kept in the URL", () => {
    const chosen = state({ q: "x", photo: "old", photoAge: 24, seen: "since", since: "2026-10-01", former: "show" });
    const params = serializeListState(chosen);
    expect(params.toString()).toBe("q=x&photo=old&photo_age=24&since=2026-10-01&former=show");
    expect(parseListState(params)).toEqual(chosen);
    expect(parseListState(new URLSearchParams("seen=never"))).toEqual(state({ seen: "never" }));
    expect(parseListState(new URLSearchParams("since=yesterday&photo_age=5&photo=all&former=no"))).toEqual(EMPTY_STATE);
    expect(clearFilters(chosen)).toEqual(state({ q: "x" }));
  });
});

describe("sorting", () => {
  const now = new Date(2026, 9, 25);

  it("is by name by default, and by any column either way with empty values last", () => {
    expect(rows(sortRows(SCHEMA, ROWS, { key: "name", desc: false }, now))).toEqual([4, 5, 3, 2]);
    expect(rows(sortRows(SCHEMA, ROWS, { key: "tag", desc: true }, now))).toEqual([2, 5, 3, 4]);
    expect(rows(sortRows(SCHEMA, ROWS, { key: "price", desc: false }, now))).toEqual([4, 3, 2, 5]);
    expect(rows(sortRows(SCHEMA, ROWS, { key: "c:Marathon", desc: false }, now))).toEqual([
      2, 5, 3, 4,
    ]);
  });
});

describe("URL state", () => {
  it("round-trips and leaves defaults out", () => {
    const chosen = state({
      q: "lith",
      sort: { key: "c:Marathon", desc: true },
      genus: ["Lithops", "Conophytum"],
      tagged: "yes",
      custom: { Marathon: ["Конкурсный 2023", ""] },
    });
    const params = serializeListState(chosen);
    expect(params.toString()).toBe(
      "q=lith&sort=-c%3AMarathon&genus=Lithops&genus=Conophytum&tag=yes" +
        "&c.Marathon=%D0%9A%D0%BE%D0%BD%D0%BA%D1%83%D1%80%D1%81%D0%BD%D1%8B%D0%B9+2023&c.Marathon=",
    );
    expect(parseListState(params)).toEqual(chosen);
    expect(serializeListState(EMPTY_STATE).toString()).toBe("");
    expect(parseListState(new URLSearchParams("tag=maybe&c.=x"))).toEqual(EMPTY_STATE);
  });

  it("takes any custom column name, even one an object has built in", () => {
    const parsed = parseListState(new URLSearchParams("c.__proto__=x&c.constructor=y"));
    expect(Object.keys(parsed.custom)).toEqual(["__proto__", "constructor"]);
    expect(own(parsed.custom, "__proto__")).toEqual(["x"]);
    expect(own({}, "__proto__")).toBeUndefined();
    expect(rows(filterRows(ROWS, parsed, NOW))).toEqual([]);
    expect(serializeListState(parsed).toString()).toBe("c.__proto__=x&c.constructor=y");
  });
});
