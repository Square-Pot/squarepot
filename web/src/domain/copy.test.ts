// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";
import type { Collection, Sync } from "../api/types";
import { applySync, plantsOf } from "./copy";
import { plant } from "./fixtures";

const MAIN: Collection = {
  id: "main",
  name: "Main",
  plant_count: 2,
  synced_at: null,
  error: null,
  custom_columns: [],
  sheet_url: null,
};

const sync = (change: Partial<Sync>): Sync => ({
  kind: "delta",
  cursor: "c2",
  schema_version: 1,
  collections: [],
  removed_collections: [],
  plants: [],
  removed_plants: [],
  ...change,
});

describe("applySync", () => {
  const start = applySync(
    null,
    sync({ kind: "full", cursor: "c1", collections: [MAIN], plants: [plant(2, "000001", {}), plant(3, null, {})] }),
  );

  it("applies a delta without touching the old copy", () => {
    const next = applySync(start, sync({ plants: [plant(4, null, {})], removed_plants: ["main:2"] }));
    expect(plantsOf(next, "main").map((p) => p.row)).toEqual([3, 4]);
    expect(next.cursor).toBe("c2");
    expect(plantsOf(start, "main").map((p) => p.row)).toEqual([2, 3]);
  });

  it("replaces everything on a full sync", () => {
    const next = applySync(start, sync({ kind: "full", plants: [plant(9, null, {})] }));
    expect([...next.plants.keys()]).toEqual(["main:9"]);
    expect(next.collections.size).toBe(0);
  });
});
