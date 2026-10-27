// SPDX-License-Identifier: AGPL-3.0-or-later
// Signed thumbnail addresses of the plants' main photos, for the list. An image
// cannot send the token, so the addresses come from `POST /api/v1/photos/thumbnails`
// in batches, and are kept until shortly before they expire.
import { useEffect, useSyncExternalStore } from "react";
import { api } from "./api/client";

const BATCH = 200;
/** How often a page left open asks again. */
const REASK_MS = 5 * 60_000;
/** Ask again this long before the addresses expire: more than `REASK_MS`, so no image gets an expired one. */
const EXPIRY_MARGIN_MS = 10 * 60_000;
/** After a failure or with photos off, how long to wait before asking again. */
const RETRY_MS = 5 * 60_000;

interface Signed {
  /** `null`: the server has no such photo, or photos are off. */
  url: string | null;
  until: number;
}

const signed = new Map<string, Signed>();
const asking = new Set<string>();
const listeners = new Set<() => void>();
let version = 0;
/** Raised by a reset, so an answer to a request made before it is dropped. */
let generation = 0;

function changed(): void {
  version += 1;
  for (const listener of listeners) listener();
}

const fresh = (id: string, now: number): boolean => (signed.get(id)?.until ?? 0) > now;

async function sign(ids: string[]): Promise<void> {
  const asked = generation;
  for (const id of ids) asking.add(id);
  let answer: Map<string, Signed>;
  try {
    const response = await api.POST("/api/v1/photos/thumbnails", { body: { ids } });
    const until = response.data ? Date.parse(response.data.expires_at) - EXPIRY_MARGIN_MS : Date.now() + RETRY_MS;
    // Photos off (503) or another failure: no thumbnails for a while, the list works without them.
    answer = new Map(ids.map((id) => [id, { url: response.data?.urls[id] ?? null, until }]));
  } catch {
    answer = new Map(ids.map((id) => [id, { url: null, until: Date.now() + RETRY_MS }]));
  }
  // A reset since the request (the token forgotten) makes its answer worthless.
  if (asked !== generation) return;
  for (const [id, entry] of answer) {
    signed.set(id, entry);
    asking.delete(id);
  }
  changed();
}

/** Ask for the addresses of `ids` that are missing or about to expire. */
export function requestThumbnails(ids: string[]): void {
  const now = Date.now();
  const missing = [...new Set(ids)].filter((id) => !fresh(id, now) && !asking.has(id));
  for (let at = 0; at < missing.length; at += BATCH) void sign(missing.slice(at, at + BATCH));
}

/** Forget every address, as when the token is forgotten. */
export function resetThumbnails(): void {
  generation += 1;
  signed.clear();
  asking.clear();
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
    }, REASK_MS);
    return () => {
      clearInterval(timer);
    };
  }, [key]);
  useSyncExternalStore(subscribe, () => version);
  return (id) => (id ? (signed.get(id)?.url ?? null) : null);
}
