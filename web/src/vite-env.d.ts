// SPDX-License-Identifier: AGPL-3.0-or-later
/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** The source commit this app was built from (task #185); unset in `npm run dev`. */
  readonly SQUAREPOT_COMMIT?: string;
}
