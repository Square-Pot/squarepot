// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";
import type { LabelTemplate } from "../api/types";
import { plant, SCHEMA } from "./fixtures";
import {
  clampSkip,
  cleanFields,
  defaultFields,
  defaultKind,
  grid,
  pageCount,
  printOrder,
  slotAt,
  toEntries,
} from "./print";
import { makeRows } from "./query";

// The vertical template on main: 15×60 mm labels, 10 mm margins, 2 mm gaps, on A4.
const VERTICAL: LabelTemplate["layout"] = {
  orientation: "vertical",
  width_mm: 15,
  height_mm: 60,
  burial_mm: 25,
  band_mm: 0,
  chamfer_mm: 0,
  burial_text: false,
  module_mm: 1.2,
  max_lines: 8,
  caption_box: true,
  show_number: true,
  page: "a4",
  margin_mm: 10,
  gap_mm: 2,
  cut_lines: true,
};

describe("grid", () => {
  it("fits labels as the server does", () => {
    // (210 - 20 + 2) / 17 = 11.29 columns, (297 - 20 + 2) / 62 = 4.5 rows.
    expect(grid(VERTICAL)).toEqual({ columns: 11, rows: 4, perPage: 44 });
    expect(grid({ ...VERTICAL, page: "letter" }).columns).toBe(11);
  });

  it("finds the place under a click, gaps belonging to the place before", () => {
    expect(slotAt(VERTICAL, 10.5, 10.5)).toBe(0);
    expect(slotAt(VERTICAL, 26, 11)).toBe(0); // in the gap after the first label
    expect(slotAt(VERTICAL, 28, 11)).toBe(1);
    expect(slotAt(VERTICAL, 11, 73)).toBe(11);
    expect(slotAt(VERTICAL, 5, 5)).toBeNull();
    expect(slotAt(VERTICAL, 205, 11)).toBeNull();
  });

  it("keeps skipped places within a page when the label type changes", () => {
    // 30 places chosen on a vertical sheet (44 a page), then the selection turns horizontal (16).
    expect(clampSkip(30, 44)).toBe(30);
    expect(clampSkip(30, 16)).toBe(15);
    expect(clampSkip(-1, 16)).toBe(0);
    expect(clampSkip(3, 0)).toBe(0);
  });

  it("counts pages with the skipped places", () => {
    expect(pageCount(0, 0, 44)).toBe(1);
    expect(pageCount(44, 0, 44)).toBe(1);
    expect(pageCount(44, 1, 44)).toBe(2);
  });
});

const ROWS = makeRows(SCHEMA, [
  plant(2, "000003", { genus: "Lithops", label_type: "h" }),
  plant(3, "000001", { genus: "Conophytum" }),
  plant(4, "000002", { genus: "Lithops", label_type: "h" }),
]);

describe("label type and order", () => {
  it("defaults to the type most plants ask for, vertical on a tie", () => {
    expect(defaultKind(ROWS)).toBe("horizontal");
    expect(defaultKind(ROWS.slice(0, 2))).toBe("vertical");
    expect(defaultKind([])).toBe("vertical");
  });

  it("keeps the list order or sorts by number", () => {
    expect(printOrder(ROWS, "list").map((row) => row.plant.row)).toEqual([2, 3, 4]);
    expect(printOrder(ROWS, "tag").map((row) => row.plant.row)).toEqual([3, 4, 2]);
  });
});

describe("fields", () => {
  it("are schema fields or custom columns in a request", () => {
    expect(toEntries(["name", "ex", "c:Marathon"])).toEqual([{ field: "name" }, { field: "ex" }, { custom: "Marathon" }]);
  });

  it("default to the presets", () => {
    expect(defaultFields(SCHEMA, "vertical")).toEqual({ caption: ["field_number", "name", "ex"], extra: [] });
  });

  it("drop saved fields that are gone and keep the name in the caption", () => {
    const fallback = { caption: ["name"], extra: [] };
    const allowed = ["name", "ex", "c:Marathon"];
    expect(cleanFields({ caption: ["ex", "gone", "ex"], extra: ["name", "c:Marathon"] }, allowed, fallback)).toEqual({
      caption: ["name", "ex"],
      extra: ["c:Marathon"],
    });
    expect(cleanFields("junk", allowed, fallback)).toBe(fallback);
  });
});
