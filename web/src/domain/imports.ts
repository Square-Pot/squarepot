// SPDX-License-Identifier: AGPL-3.0-or-later
// Batch photo import (ADR 0008): how the review page counts the pack, and how
// «a number or a name» becomes the plant a photo is filed into.
import type { ImportedPhoto } from "../api/types";

/** The groups the page shows: the reader at work, the queue that waits for the
 * owner, and the two ways a photo leaves it. */
export type ImportGroup = "reading" | "review" | "filed" | "discarded";

export function importGroup(photo: ImportedPhoto): ImportGroup {
  switch (photo.state) {
    case "filed":
      return "filed";
    case "discarded":
      return "discarded";
    case "review":
      return "review";
    default:
      return "reading"; // queued, decoding, decoded
  }
}

export interface ImportCounts {
  reading: number;
  review: number;
  filed: number;
  discarded: number;
}

export function importCounts(photos: ImportedPhoto[]): ImportCounts {
  const counts: ImportCounts = { reading: 0, review: 0, filed: 0, discarded: 0 };
  for (const photo of photos) counts[importGroup(photo)] += 1;
  return counts;
}

/** The plant a six-digit query names, with leading zeros added as on the label;
 * `null` when the text cannot be a plant number. */
export function normalizeTag(query: string): string | null {
  const digits = query.trim().replace(/\D/g, "");
  if (!digits || digits.length > 6) return null;
  const tag = digits.padStart(6, "0");
  return tag === "000000" ? null : tag;
}

/** A name as it is typed, for matching against the sheet's Latin names. */
export function fold(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export interface PlantLookup {
  tag: string;
  name: string;
}

export type TagLookup =
  | { status: "found"; tag: string; name: string }
  | { status: "none" }
  | { status: "ambiguous" };

/** What «004217», «4217» or «demoa th» names: one numbered plant of the collection. */
export function resolveTag(query: string, plants: PlantLookup[]): TagLookup {
  const trimmed = query.trim();
  if (!trimmed) return { status: "none" };
  if (/^\d+$/.test(trimmed)) {
    const tag = normalizeTag(trimmed);
    const byTag = tag ? plants.find((plant) => plant.tag === tag) : undefined;
    return byTag ? { status: "found", tag: byTag.tag, name: byTag.name } : { status: "none" };
  }
  const words = fold(trimmed).split(" ").filter(Boolean);
  if (!words.length) return { status: "none" };
  const matches = new Map<string, string>();
  for (const plant of plants) {
    const name = fold(plant.name);
    if (!name) continue;
    if (words.every((word) => name.startsWith(word) || name.includes(` ${word}`))) {
      matches.set(plant.tag, plant.name);
    }
  }
  const only = [...matches.entries()][0];
  if (matches.size === 1 && only) return { status: "found", tag: only[0], name: only[1] };
  return matches.size ? { status: "ambiguous" } : { status: "none" };
}
