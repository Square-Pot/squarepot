// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";
import { plant, SCHEMA } from "./fixtures";
import {
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
    expect(rows(filterRows(ROWS, state({ genus: ["Lithops", "Conophytum"] })))).toEqual([2, 3, 4, 5]);
    expect(
      rows(filterRows(ROWS, state({ genus: ["Conophytum"], custom: { Marathon: ["Конкурсный 2023"] } }))),
    ).toEqual([5]);
    expect(rows(filterRows(ROWS, state({ custom: { Marathon: [""] } })))).toEqual([4]);
    expect(rows(filterRows(ROWS, state({ tagged: "no" })))).toEqual([4]);
  });

  it("count each value under the other groups, listing values with none", () => {
    const result = facets(ROWS, state({ genus: ["Lithops"] }), ["Marathon"]);
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
    expect(rows(filterRows(ROWS, parsed))).toEqual([]);
    expect(serializeListState(parsed).toString()).toBe("c.__proto__=x&c.constructor=y");
  });
});
