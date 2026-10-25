// SPDX-License-Identifier: AGPL-3.0-or-later
// The app's copy of the server's data: the field schema, label templates and
// every collection's plants. Loaded once, then brought up to date with deltas
// every minute and whenever the tab comes back into view.
import { useEffect, useSyncExternalStore } from "react";
import { api, apiError } from "./api/client";
import type { FieldSchema, LabelTemplate } from "./api/types";
import { applySync, type Copy } from "./domain/copy";

export interface DataState {
  schema: FieldSchema | null;
  templates: LabelTemplate[];
  copy: Copy | null;
  /** Why the last refresh failed; the copy, if any, stays. */
  error: string | null;
}

const EMPTY: DataState = { schema: null, templates: [], copy: null, error: null };
const REFRESH_MS = 60_000;

let state = EMPTY;
let running: Promise<void> | null = null;
const listeners = new Set<() => void>();

function update(change: Partial<DataState>): void {
  state = { ...state, ...change };
  for (const listener of listeners) listener();
}

async function load(): Promise<void> {
  const sync = await api.GET("/api/v1/sync", {
    params: { query: { cursor: state.copy?.cursor ?? null } },
  });
  if (!sync.data) throw apiError(sync.response, sync.error);
  let { schema, templates } = state;
  if (schema?.version !== sync.data.schema_version) {
    const fetched = await api.GET("/api/v1/schema");
    if (!fetched.data) throw apiError(fetched.response, fetched.error);
    schema = fetched.data;
  }
  if (!templates.length) {
    const fetched = await api.GET("/api/v1/labels/templates");
    if (!fetched.data) throw apiError(fetched.response, fetched.error);
    templates = fetched.data;
  }
  update({ schema, templates, copy: applySync(state.copy, sync.data), error: null });
}

export function refresh(): Promise<void> {
  running ??= load()
    .catch((error: unknown) => {
      update({ error: error instanceof Error ? error.message : String(error) });
    })
    .finally(() => {
      running = null;
    });
  return running;
}

/** Forget everything, as when the token is forgotten. */
export function resetData(): void {
  state = EMPTY;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useData(): DataState {
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => {
      void refresh();
    }, REFRESH_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);
  return useSyncExternalStore(subscribe, () => state);
}
