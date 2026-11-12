// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";
import { commitUrl, shortCommit, versionLine } from "./version";

describe("shortCommit", () => {
  it("takes the first seven characters", () => {
    expect(shortCommit("2cd4856ac59fb4f0ee6e0ce71e28e7b3ed2db17a")).toBe("2cd4856");
  });
  it("keeps a short commit as it is", () => {
    expect(shortCommit("2cd4856")).toBe("2cd4856");
  });
});

describe("versionLine", () => {
  it("joins the version and the short commit", () => {
    expect(versionLine("0.1.0", "2cd4856ac59fb4f0ee6e0ce71e28e7b3ed2db17a")).toBe("0.1.0 · 2cd4856");
  });
  it("says dev without a commit", () => {
    expect(versionLine("0.1.0", "")).toBe("0.1.0 · dev");
  });
});

describe("commitUrl", () => {
  it("links to the public commit", () => {
    expect(commitUrl("2cd4856ac59fb4f0ee6e0ce71e28e7b3ed2db17a")).toBe(
      "https://github.com/Square-Pot/squarepot/commit/2cd4856ac59fb4f0ee6e0ce71e28e7b3ed2db17a",
    );
  });
  it("links nowhere without a commit", () => {
    expect(commitUrl("")).toBeNull();
  });
});
