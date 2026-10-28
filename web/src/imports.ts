// SPDX-License-Identifier: AGPL-3.0-or-later
// A batch import (ADR 0008, stage 2): the owner's pack, sent one photo at a
// time; the reader's progress, asked again while it works; and the queue that
// waits for the owner to file or discard each photo.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, apiError } from "./api/client";
import { getToken, setToken } from "./api/token";
import type { ImportedPhoto } from "./api/types";
import { refresh } from "./data";
import { newPhotoId } from "./domain/photos";

/** Ask again this long before the staged addresses expire. */
const EXPIRY_MARGIN_MS = 5 * 60_000;
/** While the pack is being read, ask again this often. */
const WORKING_MS = 5_000;

export interface ImportUpload {
  /** The import's id, chosen here, so sending it again does not make a copy. */
  id: string;
  file: File;
  state: "waiting" | "sending" | "done" | "failed";
  error: string | null;
}

export interface Imports {
  /** The photos still waiting — queued, decoding, decoded or in review —
   * oldest first; `null` until loaded. */
  photos: ImportedPhoto[] | null;
  error: string | null;
  /** `true` when the server answers that photos are not set up on it. */
  unavailable: boolean;
  /** What this visit filed or discarded, kept here because the list holds
   * only the photos still waiting. */
  done: { filed: number; discarded: number };
  uploads: ImportUpload[];
  upload: (files: File[]) => void;
  retry: (id: string) => void;
  clearUploads: () => void;
  file: (id: string, tag: string) => Promise<void>;
  discard: (id: string) => Promise<void>;
}

async function list(): Promise<ImportedPhoto[]> {
  const response = await api.GET("/api/v1/imports");
  if (!response.data) throw apiError(response.response, response.error);
  return response.data;
}

async function send(upload: ImportUpload): Promise<void> {
  const query = new URLSearchParams({ file_time: new Date(upload.file.lastModified).toISOString() });
  const token = getToken();
  const response = await fetch(`/api/v1/imports/${upload.id}?${query.toString()}`, {
    method: "PUT",
    headers: { "Content-Type": upload.file.type, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: upload.file,
  });
  if (response.status === 401) setToken(null);
  if (!response.ok) throw apiError(response, await response.json().catch(() => null));
}

const message = (error: unknown): string => (error instanceof Error ? error.message : String(error));

/** The batch import page's server state; key the page by collection, so
 * another collection starts afresh. */
export function useImports(): Imports {
  const [photos, setPhotos] = useState<ImportedPhoto[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [done, setDone] = useState({ filed: 0, discarded: 0 });
  const [uploads, setUploads] = useState<ImportUpload[]>([]);
  const queue = useRef<ImportUpload[]>([]);
  const sending = useRef(false);

  const reload = useCallback(
    (): Promise<void> =>
      list().then(
        (loaded) => {
          setPhotos(loaded);
          setError(null);
          setUnavailable(false);
        },
        (failure: unknown) => {
          if (failure instanceof ApiError && failure.status === 503) {
            setUnavailable(true);
            setError(null);
          } else {
            setError(message(failure));
          }
        },
      ),
    [],
  );

  useEffect(() => {
    void reload();
  }, [reload]);

  // The reader works through the queue apart from the API: while it does, and
  // while our own uploads go, ask again until the pack settles.
  const working =
    (photos?.some((photo) => photo.state === "queued" || photo.state === "decoding" || photo.state === "decoded") ??
      false) ||
    uploads.some((upload) => upload.state === "waiting" || upload.state === "sending");
  useEffect(() => {
    if (!working) return;
    const timer = setInterval(() => {
      void reload();
    }, WORKING_MS);
    return () => {
      clearInterval(timer);
    };
  }, [working, reload]);

  // Staged addresses expire after a few hours: fetch the list again before they do.
  const expires =
    photos?.reduce(
      (soonest, photo) => (photo.url_expires_at ? Math.min(soonest, Date.parse(photo.url_expires_at)) : soonest),
      Infinity,
    ) ?? Infinity;
  useEffect(() => {
    if (!Number.isFinite(expires)) return;
    const timer = setTimeout(() => {
      void reload();
    }, Math.max(expires - Date.now() - EXPIRY_MARGIN_MS, 1000));
    return () => {
      clearTimeout(timer);
    };
  }, [expires, reload]);

  const setQueue = (next: ImportUpload[]) => {
    queue.current = next;
    setUploads(next);
  };
  const mark = (id: string, change: Partial<ImportUpload>) => {
    setQueue(queue.current.map((upload) => (upload.id === id ? { ...upload, ...change } : upload)));
  };

  // Uploads go one at a time, as the server's reader takes them.
  const pump = async () => {
    if (sending.current) return;
    sending.current = true;
    try {
      for (;;) {
        const next = queue.current.find((upload) => upload.state === "waiting");
        if (!next) break;
        mark(next.id, { state: "sending", error: null });
        try {
          await send(next);
          mark(next.id, { state: "done" });
          void reload();
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
    unavailable,
    done,
    uploads,
    upload: (files) => {
      setQueue([
        ...queue.current,
        ...files.map((file) => ({ id: newPhotoId(), file, state: "waiting" as const, error: null })),
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
    file: async (id, tag) => {
      await after(await api.POST("/api/v1/imports/{import_id}/file", { params: { path: { import_id: id } }, body: { tag } }));
      setDone((prev) => ({ ...prev, filed: prev.filed + 1 }));
    },
    discard: async (id) => {
      await after(await api.POST("/api/v1/imports/{import_id}/discard", { params: { path: { import_id: id } } }));
      setDone((prev) => ({ ...prev, discarded: prev.discarded + 1 }));
    },
  };
}
