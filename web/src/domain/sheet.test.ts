// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";
import { sheetRowUrl } from "./sheet";

describe("sheetRowUrl", () => {
  it("adds the row to the fragment, with or without a tab", () => {
    expect(sheetRowUrl("https://docs.google.com/spreadsheets/d/1AbC/edit#gid=0", 214)).toBe(
      "https://docs.google.com/spreadsheets/d/1AbC/edit#gid=0&range=A214",
    );
    expect(sheetRowUrl("https://docs.google.com/spreadsheets/d/1AbC/edit", 2)).toBe(
      "https://docs.google.com/spreadsheets/d/1AbC/edit#range=A2",
    );
  });
});
