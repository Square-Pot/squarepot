// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";
import { SCHEMA } from "./fixtures";
import { age, monthsSince, nameRuns, plainText } from "./names";

describe("nameRuns", () => {
  it("styles each part by the schema and skips empty ones", () => {
    const runs = nameRuns(SCHEMA, {
      genus: "lithops",
      species: "Lesliei",
      variety: " Albinica ",
      cultivar: "Storms Snowcap",
      ex: "not in the name",
    });
    expect(plainText(runs)).toBe("Lithops lesliei var. albinica ‘Storms Snowcap’");
    expect(runs.filter((run) => run.italic).map((run) => run.text)).toEqual([
      "Lithops",
      "lesliei",
      "albinica",
    ]);
  });

  it("puts the affinity in place of the epithet", () => {
    expect(plainText(nameRuns(SCHEMA, { genus: "Lithops", affinity: "lesliei" }))).toBe(
      "Lithops aff. lesliei",
    );
  });
});

describe("age", () => {
  const now = new Date(2026, 9, 25);

  it("counts whole months", () => {
    expect(monthsSince("2026-09-25", now)).toBe(1);
    expect(monthsSince("2026-09-26", now)).toBe(0);
    expect(monthsSince("2026-11-01", now)).toBeNull();
  });

  it("is months under two years, then years, from seeding before purchase", () => {
    expect(age({ seeding_date: "2025-01-10" }, now)).toEqual({ months: 21 });
    expect(age({ seeding_date: "2022-03-05", purchase_date: "2025-01-01" }, now)).toEqual({
      years: 4,
    });
    expect(age({ purchase_date: "2024-10-25" }, now)).toEqual({ years: 2 });
    expect(age({}, now)).toBeNull();
  });
});
