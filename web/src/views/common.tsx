// SPDX-License-Identifier: AGPL-3.0-or-later
// Small pieces shared by the views.
import type { Run } from "../domain/names";
import { highlight, highlightRuns } from "../domain/query";

/** A plant name, its epithets in italics, with the search match marked. */
export function Name({ runs, query = "" }: { runs: Run[]; query?: string }) {
  return (
    <>
      {highlightRuns(runs, query).map((run, i) => {
        const text = run.mark ? <mark>{run.text}</mark> : run.text;
        return run.italic ? <i key={i}>{text}</i> : <span key={i}>{text}</span>;
      })}
    </>
  );
}

/** Text with the first match of `query` marked. */
export function Marked({ text, query }: { text: string; query: string }) {
  return (
    <>
      {highlight(text, query).map((piece, i) =>
        piece.mark ? <mark key={i}>{piece.text}</mark> : <span key={i}>{piece.text}</span>,
      )}
    </>
  );
}

const ICONS = {
  search: <><circle cx="11" cy="11" r="6.5" /><path d="M16 16l4.5 4.5" /></>,
  x: <path d="M6 6l12 12M18 6L6 18" />,
  ext: <><path d="M14 4h6v6M20 4l-9 9" /><path d="M18 14v6H4V6h6" /></>,
  left: <path d="M14 6l-6 6 6 6" />,
  right: <path d="M10 6l6 6-6 6" />,
  filter: <path d="M4 6h16M7 12h10M10 18h4" />,
  cols: <><rect x="4" y="5" width="16" height="14" /><path d="M10 5v14M15 5v14" /></>,
  lock: <><rect x="5" y="11" width="14" height="9" rx="1" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></>,
  warn: <><path d="M12 4l9 16H3z" /><path d="M12 10v4.5M12 17.2v.3" /></>,
  sort: <path d="M8 5v14M5 16l3 3 3-3M16 19V5M13 8l3-3 3 3" />,
  up: <path d="M12 19V5M6 11l6-6 6 6" />,
  down: <path d="M12 5v14M6 13l6 6 6-6" />,
  back: <path d="M15 5l-7 7 7 7" />,
  key: <><circle cx="8" cy="15" r="4" /><path d="M11 12l8-8M16 7l3 3" /></>,
};

export function Icon({ name, size = 16 }: { name: keyof typeof ICONS; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICONS[name]}
    </svg>
  );
}
