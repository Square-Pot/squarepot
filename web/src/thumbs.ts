// SPDX-License-Identifier: AGPL-3.0-or-later
// Signed thumbnail addresses of the plants' main photos, for the list. An image
// cannot send the token, so the addresses come from `POST /api/v1/photos/thumbnails`
// in batches, and are kept until shortly before they expire.
import { useEffect, useSyncExternalStore } from "react";
import { api } from "./api/client";

const BATCH = 200;
/** Ask again this long before the addresses expire. */
const EXPIRY_MARGIN_MS = 5 * 60_000;

interface Signed {
  /** `null`: the server has no such photo, or photos are off. */
  url: string | null;
  until: number;
}

const signed = new Map<string, Signed>();
const asking = new Set<string>();
const listeners = new Set<() => void>();
let version = 0;

function changed(): void {
  version += 1;
  for (const listener of listeners) listener();
}

const fresh = (id: string, now: number): boolean => (signed.get(id)?.until ?? 0) > now;

async function sign(ids: string[]): Promise<void> {
  for (const id of ids) asking.add(id);
  try {
    const response = await api.POST("/api/v1/photos/thumbnails", { body: { ids } });
    const now = Date.now();
    if (response.data) {
      const until = Date.parse(response.data.expires_at) - EXPIRY_MARGIN_MS;
      for (const id of ids) signed.set(id, { url: response.data.urls[id] ?? null, until });
    } else {
      // Photos off (503) or another failure: no thumbnails for a while, the list works without them.
      for (const id of ids) signed.set(id, { url: null, until: now + EXPIRY_MARGIN_MS });
    }
  } catch {
    for (const id of ids) signed.set(id, { url: null, until: Date.now() + EXPIRY_MARGIN_MS });
  } finally {
    for (const id of ids) asking.delete(id);
    changed();
  }
}

/** Ask for the addresses of `ids` that are missing or about to expire. */
export function requestThumbnails(ids: string[]): void {
  const now = Date.now();
  const missing = [...new Set(ids)].filter((id) => !fresh(id, now) && !asking.has(id));
  for (let at = 0; at < missing.length; at += BATCH) void sign(missing.slice(at, at + BATCH));
}

/** Forget every address, as when the token is forgotten. */
export function resetThumbnails(): void {
  signed.clear();
  changed();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** The thumbnail address of each photo id it is known for, asking for the rest. */
export function useThumbnails(ids: string[]): (id: string | null) => string | null {
  const key = ids.join(",");
  useEffect(() => {
    const wanted = key ? key.split(",") : [];
    requestThumbnails(wanted);
    // Addresses expire after hours; a page left open asks again.
    const timer = setInterval(() => {
      requestThumbnails(wanted);
    }, EXPIRY_MARGIN_MS);
    return () => {
      clearInterval(timer);
    };
  }, [key]);
  useSyncExternalStore(subscribe, () => version);
  return (id) => (id ? (signed.get(id)?.url ?? null) : null);
}
