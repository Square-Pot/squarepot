// SPDX-License-Identifier: AGPL-3.0-or-later
// Links into the Google Sheet the server reads, as `Collection.sheet_url` describes.

/** The sheet opened at a plant's row: `range=A<row>` added to the address's fragment. */
export function sheetRowUrl(sheetUrl: string, row: number): string {
  return `${sheetUrl}${sheetUrl.includes("#") ? "&" : "#"}range=A${String(row)}`;
}
