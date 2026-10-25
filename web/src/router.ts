// SPDX-License-Identifier: AGPL-3.0-or-later
// Two kinds of page, so no router library: `/c/<collection>` and `/c/<collection>/p/<plant>`.
// The query string carries the list's search, filters and sort on both.
import { useSyncExternalStore, type MouseEvent } from "react";

export type Route =
  | { page: "home" }
  | { page: "list"; collection: string }
  | { page: "plant"; collection: string; plant: string };

function decode(part: string): string {
  try {
    return decodeURIComponent(part);
  } catch {
    return part;
  }
}

export function parseRoute(pathname: string): Route {
  const parts = pathname.split("/").filter(Boolean).map(decode);
  if (parts[0] === "c" && parts[1] !== undefined) {
    if (parts.length === 2) return { page: "list", collection: parts[1] };
    if (parts[2] === "p" && parts[3] !== undefined && parts.length === 4) {
      return { page: "plant", collection: parts[1], plant: parts[3] };
    }
  }
  return { page: "home" };
}

export function routePath(route: Route): string {
  switch (route.page) {
    case "home":
      return "/";
    case "list":
      return `/c/${encodeURIComponent(route.collection)}`;
    case "plant":
      return `/c/${encodeURIComponent(route.collection)}/p/${encodeURIComponent(route.plant)}`;
  }
}

const listeners = new Set<() => void>();

export function navigate(href: string, options: { replace?: boolean } = {}): void {
  if (href === location.pathname + location.search) return;
  if (options.replace) history.replaceState(null, "", href);
  else history.pushState(null, "", href);
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

const snapshot = (): string => location.pathname + location.search;

/** The current path and query, re-rendering on every navigation. */
export function useLocation(): { route: Route; params: URLSearchParams } {
  const href = useSyncExternalStore(subscribe, snapshot);
  const url = new URL(href, location.origin);
  return { route: parseRoute(url.pathname), params: url.searchParams };
}

/** A link click handled in the page, leaving modified clicks to the browser. */
export function onLinkClick(event: MouseEvent<HTMLAnchorElement>, href: string): void {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  navigate(href);
}
