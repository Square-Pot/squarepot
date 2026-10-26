// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";
import type { Photo } from "../api/types";
import { ageAt, byYear, mainPhoto, newest, pinned, uploadProblem } from "./photos";

const photo = (id: string, taken_at: string, main = false): Photo => ({
  id,
  tag: "002187",
  taken_at,
  taken_from: "camera",
  uploaded_at: taken_at,
  width: 2560,
  height: 1920,
  comment: "",
  main,
  deleted_at: null,
  url: `/large/${id}`,
  thumbnail_url: `/thumb/${id}`,
  urls_expire_at: "2026-10-26T18:00:00Z",
});

const PHOTOS = [
  photo("a", "2024-04-02T12:00:00"),
  photo("b", "2025-06-10T12:00:00"),
  photo("c", "2024-11-20T12:00:00"),
  photo("d", "2025-01-05T12:00:00"),
];

describe("timeline", () => {
  it("groups by year, newest year and photo first", () => {
    expect(byYear(PHOTOS).map((year) => [year.year, year.photos.map((p) => p.id)])).toEqual([
      ["2025", ["b", "d"]],
      ["2024", ["c", "a"]],
    ]);
    expect(byYear([])).toEqual([]);
  });

  it("counts the age from seeding, else the time in the collection from purchase", () => {
    expect(ageAt({ seeding_date: "2023-03-15" }, "2024-04-02T12:00:00")).toEqual({ from: "seeding", months: 12 });
    expect(ageAt({ purchase_date: "2024-01-01" }, "2024-04-02T12:00:00")).toEqual({ from: "purchase", months: 3 });
    expect(ageAt({ seeding_date: "2025-01-01" }, "2024-04-02T12:00:00")).toBeNull();
    expect(ageAt({}, "2024-04-02T12:00:00")).toBeNull();
  });
});

describe("main photo", () => {
  it("is the newest unless the server marks another", () => {
    expect(newest(PHOTOS)?.id).toBe("b");
    expect(mainPhoto(PHOTOS)?.id).toBe("b");
    expect(pinned(PHOTOS)).toBe(false);
    const picked = PHOTOS.map((p) => (p.id === "c" ? { ...p, main: true } : p));
    expect(mainPhoto(picked)?.id).toBe("c");
    expect(pinned(picked)).toBe(true);
    expect(mainPhoto([])).toBeUndefined();
    expect(pinned([])).toBe(false);
  });
});

describe("upload", () => {
  it("takes JPEG, PNG and WebP up to 30 MB", () => {
    expect(uploadProblem({ type: "image/jpeg", size: 1000 })).toBeNull();
    expect(uploadProblem({ type: "image/webp", size: 30 * 1024 * 1024 })).toBeNull();
    expect(uploadProblem({ type: "image/heic", size: 1000 })).toBe("type");
    expect(uploadProblem({ type: "image/png", size: 30 * 1024 * 1024 + 1 })).toBe("size");
  });
});
