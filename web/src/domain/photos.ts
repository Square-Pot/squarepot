// SPDX-License-Identifier: AGPL-3.0-or-later
// A plant's photos as the card shows them (ADR 0007): a timeline by year, the
// plant's age at each photo, and which one is the main photo.
import type { Photo } from "../api/types";
import { monthsSince, type Fields } from "./names";

/** The local calendar day of a time, as `YYYY-MM-DD`. */
export function localDay(iso: string): string {
  const date = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${String(date.getFullYear())}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export interface AgeAt {
  /** Seeding gives the plant's age; purchase only the time in the collection. */
  from: "seeding" | "purchase";
  months: number;
}

/** The plant's age when `iso` happened: from seeding, else from purchase; `null` before either or without both. */
export function ageAt(fields: Fields, iso: string): AgeAt | null {
  const seeding = fields.seeding_date;
  const from = seeding ?? fields.purchase_date;
  if (!from) return null;
  const months = monthsSince(from, new Date(iso));
  return months === null ? null : { from: seeding ? "seeding" : "purchase", months };
}

export interface Year {
  year: string;
  /** Newest first. */
  photos: Photo[];
}

/** Photos grouped by the local year they were taken, newest year and photo first. */
export function byYear(photos: Photo[]): Year[] {
  const sorted = [...photos].sort((a, b) => Date.parse(b.taken_at) - Date.parse(a.taken_at));
  const years: Year[] = [];
  for (const photo of sorted) {
    const year = localDay(photo.taken_at).slice(0, 4);
    const last = years.at(-1);
    if (last?.year === year) last.photos.push(photo);
    else years.push({ year, photos: [photo] });
  }
  return years;
}

export const newest = (photos: Photo[]): Photo | undefined =>
  photos.reduce<Photo | undefined>((best, photo) => (!best || Date.parse(photo.taken_at) > Date.parse(best.taken_at) ? photo : best), undefined);

/** The main photo: the one the server marks, else the newest. */
export const mainPhoto = (photos: Photo[]): Photo | undefined => photos.find((photo) => photo.main) ?? newest(photos);

/** Whether the owner picked a main photo other than the newest, so new photos do not replace it. */
export function pinned(photos: Photo[]): boolean {
  const main = mainPhoto(photos);
  return !!main && main !== newest(photos);
}

export const UPLOAD_TYPES = ["image/jpeg", "image/png", "image/webp"];
/** The server's limit per photo. */
export const UPLOAD_MAX_BYTES = 30 * 1024 * 1024;

/** Why a file cannot be uploaded, or `null` when it can. */
export function uploadProblem(file: { type: string; size: number }): "type" | "size" | null {
  if (!UPLOAD_TYPES.includes(file.type)) return "type";
  if (file.size > UPLOAD_MAX_BYTES) return "size";
  return null;
}

/**
 * A random UUID for a new photo. `crypto.randomUUID` exists only in secure
 * contexts, so over plain http (a LAN address) it is built from random bytes.
 */
export function newPhotoId(source: Pick<Crypto, "getRandomValues"> & Partial<Pick<Crypto, "randomUUID">> = crypto): string {
  if (typeof source.randomUUID === "function") return source.randomUUID();
  const bytes = source.getRandomValues(new Uint8Array(16));
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
