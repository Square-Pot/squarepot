// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";
import { parseRoute, routePath, type Route } from "./router";

describe("routes", () => {
  it.each<[string, Route]>([
    ["/", { page: "home" }],
    ["/c/main", { page: "list", collection: "main" }],
    ["/c/main/", { page: "list", collection: "main" }],
    ["/c/main/p/main%3A004217", { page: "plant", collection: "main", plant: "main:004217" }],
    ["/c/main/print", { page: "print", collection: "main" }],
    ["/c/main/import", { page: "import", collection: "main" }],
    ["/c/main/x/1", { page: "home" }],
    ["/elsewhere", { page: "home" }],
  ])("%s", (path, route) => {
    expect(parseRoute(path)).toEqual(route);
  });

  it("round-trips a plant id with any characters", () => {
    const route: Route = { page: "plant", collection: "main", plant: "main:a/b?c" };
    expect(parseRoute(routePath(route))).toEqual(route);
  });
});
