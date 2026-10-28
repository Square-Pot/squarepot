// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";
import type { ImportedPhoto } from "../api/types";
import { fold, importCounts, importGroup, normalizeTag, resolveTag, type PlantLookup } from "./imports";

const photo = (over: Partial<ImportedPhoto>): ImportedPhoto => ({
  id: "0d2ce6ac-7563-4a1e-9e7a-2b64a3e0f001",
  state: "queued",
  reason: null,
  numbers: [],
  tag: null,
  file_time: null,
  uploaded_at: "2026-10-26T10:00:00Z",
  url: null,
  url_expires_at: null,
  ...over,
});

describe("importGroup", () => {
  it("puts the reader's states together and keeps the rest apart", () => {
    expect(importGroup(photo({ state: "queued" }))).toBe("reading");
    expect(importGroup(photo({ state: "decoding" }))).toBe("reading");
    expect(importGroup(photo({ state: "decoded" }))).toBe("reading");
    expect(importGroup(photo({ state: "review", reason: "no_code" }))).toBe("review");
    expect(importGroup(photo({ state: "filed", tag: "004217" }))).toBe("filed");
    expect(importGroup(photo({ state: "discarded" }))).toBe("discarded");
  });
});

describe("importCounts", () => {
  it("counts each group", () => {
    const counts = importCounts([
      photo({ state: "queued" }),
      photo({ state: "decoding" }),
      photo({ state: "decoded" }),
      photo({ state: "review", reason: "several_numbers", numbers: ["004217", "004218"] }),
      photo({ state: "filed", tag: "004217" }),
      photo({ state: "discarded", reason: "expired" }),
    ]);
    expect(counts).toEqual({ reading: 3, review: 1, filed: 1, discarded: 1 });
  });
});

describe("normalizeTag", () => {
  it("adds the label's leading zeros", () => {
    expect(normalizeTag("4217")).toBe("004217");
    expect(normalizeTag(" 004217 ")).toBe("004217");
  });
  it("refuses what cannot be a number", () => {
    expect(normalizeTag("1234567")).toBeNull();
    expect(normalizeTag("000000")).toBeNull();
    expect(normalizeTag("")).toBeNull();
    expect(normalizeTag("фото")).toBeNull();
  });
});

describe("fold", () => {
  it("keeps Latin letters, digits and spaces only", () => {
    expect(fold("Démoa theréseae subsp. minor")).toBe("demoa thereseae subsp minor");
  });
});

describe("resolveTag", () => {
  const plants: PlantLookup[] = [
    { tag: "004217", name: "Demoa theresae" },
    { tag: "004218", name: "Demoa thermarum" },
    { tag: "004219", name: "Samplera aurea" },
  ];

  it("finds a plant by its number, zeros or not", () => {
    expect(resolveTag("004217", plants)).toEqual({ status: "found", tag: "004217", name: "Demoa theresae" });
    expect(resolveTag("4217", plants)).toEqual({ status: "found", tag: "004217", name: "Demoa theresae" });
  });

  it("refuses a number no plant has", () => {
    expect(resolveTag("999999", plants)).toEqual({ status: "none" });
  });

  it("finds a plant by the first letters of its name words", () => {
    expect(resolveTag("demoa therm", plants)).toEqual({ status: "found", tag: "004218", name: "Demoa thermarum" });
    expect(resolveTag("samplera au", plants)).toEqual({ status: "found", tag: "004219", name: "Samplera aurea" });
    expect(resolveTag("therm", plants)).toEqual({ status: "found", tag: "004218", name: "Demoa thermarum" });
  });

  it("asks for the number when several plants match", () => {
    expect(resolveTag("demoa", plants)).toEqual({ status: "ambiguous" });
    expect(resolveTag("demoa th", plants)).toEqual({ status: "ambiguous" });
  });

  it("says nothing about an empty line", () => {
    expect(resolveTag("  ", plants)).toEqual({ status: "none" });
  });
});
