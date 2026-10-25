// SPDX-License-Identifier: AGPL-3.0-or-later
// The API token, pasted once and kept in this browser only. It goes out only as
// `Authorization: Bearer`, never in a URL, and is never logged.
import { useSyncExternalStore } from "react";

const KEY = "squarepot.token";
const listeners = new Set<() => void>();
let memory: string | null = null;

function read(): string | null {
  try {
    return localStorage.getItem(KEY) ?? memory;
  } catch {
    return memory;
  }
}

export function getToken(): string | null {
  return read();
}

export function setToken(token: string | null): void {
  memory = token;
  try {
    if (token === null) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, token);
  } catch {
    // Storage is blocked: the token lives until the tab closes.
  }
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === KEY) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export const useToken = (): string | null => useSyncExternalStore(subscribe, read);
