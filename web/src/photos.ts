// SPDX-License-Identifier: AGPL-3.0-or-later
// One plant's photos from the server: the list with its expiring addresses,
// uploads one at a time, and the owner's changes. Each change also refreshes
// the copy, so the list's photo and visit columns follow.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiError } from "./api/client";
import { getToken, setToken } from "./api/token";
import type { Photo } from "./api/types";
import { refresh } from "./data";

/** Ask again this long before the addresses expire. */
const EXPIRY_MARGIN_MS = 5 * 60_000;

export interface Upload {
  /** The photo's id, chosen here, so sending it again does not make a copy. */
  id: string;
  file: File;
  state: "waiting" | "sending" | "done" | "failed";
  error: string | null;
}

export interface PlantPhotos {
  /** Every photo, deleted ones of the last 30 days too; `null` until loaded. */
  photos: Photo[] | null;
  error: string | null;
  uploads: Upload[];
  upload: (files: File[]) => void;
  retry: (id: string) => void;
  clearUploads: () => void;
  change: (id: string, change: { comment?: string; taken_at?: string }) => Promise<void>;
  remove: (id: string) => Promise<void>;
  restore: (id: string) => Promise<void>;
  /** `null` makes the newest the main photo again. */
  chooseMain: (id: string | null) => Promise<void>;
}

async function list(tag: string): Promise<Photo[]> {
  const response = await api.GET("/api/v1/plants/by-tag/{tag}/photos", {
    params: { path: { tag }, query: { deleted: true } },
  });
  if (!response.data) throw apiError(response.response, response.error);
  return response.data;
}

async function send(tag: string, upload: Upload): Promise<void> {
  const query = new URLSearchParams({ tag, taken_at: new Date(upload.file.lastModified).toISOString() });
  const token = getToken();
  const response = await fetch(`/api/v1/photos/${upload.id}?${query.toString()}`, {
    method: "PUT",
    headers: { "Content-Type": upload.file.type, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: upload.file,
  });
  if (response.status === 401) setToken(null);
  if (!response.ok) throw apiError(response, await response.json().catch(() => null));
}

const message = (error: unknown): string => (error instanceof Error ? error.message : String(error));

/** The photos of the plant numbered `tag`; key the component by `tag`, so another plant starts afresh. */
export function usePlantPhotos(tag: string | null): PlantPhotos {
  const [photos, setPhotos] = useState<Photo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const queue = useRef<Upload[]>([]);
  const sending = useRef(false);

  const reload = useCallback(async () => {
    if (!tag) return;
    try {
      setPhotos(await list(tag));
      setError(null);
    } catch (failure) {
      setError(message(failure));
    }
  }, [tag]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Signed addresses expire after a few hours: fetch the list again before they do.
  const expires = photos?.reduce((soonest, photo) => Math.min(soonest, Date.parse(photo.urls_expire_at)), Infinity) ?? Infinity;
  useEffect(() => {
    if (!Number.isFinite(expires)) return;
    const timer = setTimeout(() => {
      void reload();
    }, Math.max(expires - Date.now() - EXPIRY_MARGIN_MS, 1000));
    return () => {
      clearTimeout(timer);
    };
  }, [expires, reload]);

  const setQueue = (next: Upload[]) => {
    queue.current = next;
    setUploads(next);
  };
  const mark = (id: string, change: Partial<Upload>) => {
    setQueue(queue.current.map((upload) => (upload.id === id ? { ...upload, ...change } : upload)));
  };

  // Uploads go one at a time, as the server processes them.
  const pump = async () => {
    if (!tag || sending.current) return;
    sending.current = true;
    try {
      for (;;) {
        const next = queue.current.find((upload) => upload.state === "waiting");
        if (!next) break;
        mark(next.id, { state: "sending", error: null });
        try {
          await send(tag, next);
          mark(next.id, { state: "done" });
          void reload();
          void refresh();
        } catch (failure) {
          mark(next.id, { state: "failed", error: message(failure) });
        }
      }
    } finally {
      sending.current = false;
    }
  };

  const after = async (response: { response: Response; error?: unknown }) => {
    if (!response.response.ok) throw apiError(response.response, response.error);
    await reload();
    void refresh();
  };

  return {
    photos,
    error,
    uploads,
    upload: (files) => {
      setQueue([
        ...queue.current,
        ...files.map((file) => ({ id: crypto.randomUUID(), file, state: "waiting" as const, error: null })),
      ]);
      void pump();
    },
    retry: (id) => {
      mark(id, { state: "waiting", error: null });
      void pump();
    },
    clearUploads: () => {
      setQueue(queue.current.filter((upload) => upload.state === "waiting" || upload.state === "sending"));
    },
    change: async (id, change) => {
      await after(await api.PATCH("/api/v1/photos/{photo_id}", { params: { path: { photo_id: id } }, body: change }));
    },
    remove: async (id) => {
      await after(await api.DELETE("/api/v1/photos/{photo_id}", { params: { path: { photo_id: id } } }));
    },
    restore: async (id) => {
      await after(await api.POST("/api/v1/photos/{photo_id}/restore", { params: { path: { photo_id: id } } }));
    },
    chooseMain: async (id) => {
      if (!tag) return;
      await after(
        await api.PUT("/api/v1/plants/by-tag/{tag}/main-photo", { params: { path: { tag } }, body: { photo_id: id } }),
      );
    },
  };
}
