// SPDX-License-Identifier: AGPL-3.0-or-later
import type { components } from "./schema";

type Schemas = components["schemas"];

export type Plant = Schemas["Plant"];
export type Collection = Schemas["Collection"];
export type FieldSchema = Schemas["FieldSchema"];
export type FieldDefinition = Schemas["FieldDefinition"];
export type Display = Schemas["Display"];
export type LabelTemplate = Schemas["LabelTemplate"];
export type Sync = Schemas["Sync"];
export type LocalizedLabel = Schemas["Label"];
export type InvalidCell = Schemas["InvalidCell"];
