// SPDX-License-Identifier: AGPL-3.0-or-later
// What the app says about its own build (task #185): the package version and
// the source commit it was made from. The commit comes from the
// SQUAREPOT_COMMIT build-time environment variable; without it the app says
// `dev`, and building never needs .git.
import { version } from "../package.json";

const COMMIT_URL = "https://github.com/Square-Pot/squarepot/commit/";

/** The short form GitHub shows, enough to name a commit. */
export function shortCommit(commit: string): string {
  return commit.slice(0, 7);
}

/** `0.1.0 · a1b2c3d`, or `0.1.0 · dev` when built without a commit. */
export function versionLine(appVersion: string, commit: string): string {
  return `${appVersion} · ${commit ? shortCommit(commit) : "dev"}`;
}

/** Where the full commit can be read, or `null` without one. */
export function commitUrl(commit: string): string | null {
  return commit ? COMMIT_URL + commit : null;
}

const COMMIT = import.meta.env.SQUAREPOT_COMMIT ?? "";

/** The commit this build was made from; empty in `npm run dev`. */
export const BUILD_COMMIT = COMMIT;
/** `0.1.0 · a1b2c3d`, or `0.1.0 · dev`, for this build. */
export const BUILD_LINE = versionLine(version, COMMIT);
