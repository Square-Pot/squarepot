// SPDX-License-Identifier: AGPL-3.0-or-later
// Test data: the real field schema's rules, cut to what the tests use.
import type { FieldSchema, Plant } from "../api/types";

export const SCHEMA: FieldSchema = {
  version: 1,
  fields: [
    { key: "tag", type: "text", label: { en: "Tag", ru: "Бирка" }, group: "basic" },
    {
      key: "field_number",
      type: "text",
      label: { en: "Field number", ru: "Полевой номер" },
      group: "basic",
      display: { case: "upper" },
    },
    {
      key: "genus",
      type: "text",
      label: { en: "Genus", ru: "Род" },
      group: "basic",
      display: { italic: true, case: "title" },
    },
    {
      key: "affinity",
      type: "text",
      label: { en: "Affinity", ru: "Близкий к" },
      group: "basic",
      display: { prefix: "aff.", italic: true, case: "as-is" },
    },
    {
      key: "species",
      type: "text",
      label: { en: "Species", ru: "Вид" },
      group: "basic",
      display: { italic: true, case: "lower" },
    },
    {
      key: "variety",
      type: "text",
      label: { en: "Variety", ru: "Разновидность" },
      group: "basic",
      display: { prefix: "var.", italic: true, case: "lower" },
    },
    {
      key: "cultivar",
      type: "text",
      label: { en: "Cultivar", ru: "Сорт" },
      group: "basic",
      display: { quote: true, case: "as-is" },
    },
    { key: "ex", type: "text", label: { en: "Ex", ru: "Ex" }, group: "basic" },
    {
      key: "seeding_date",
      type: "date",
      label: { en: "Seeding date", ru: "Дата посева" },
      group: "extra",
    },
    {
      key: "purchase_date",
      type: "date",
      label: { en: "Purchase date", ru: "Дата покупки" },
      group: "extra",
    },
    { key: "price", type: "decimal", label: { en: "Price", ru: "Цена" }, group: "extra" },
  ],
  computed: [
    {
      key: "name",
      label: { en: "Name", ru: "Название" },
      from: ["genus", "affinity", "species", "variety", "cultivar"],
    },
    {
      key: "age",
      label: { en: "Age", ru: "Возраст" },
      from: ["seeding_date", "purchase_date"],
    },
  ],
  presets: [{ key: "label", label: { en: "Label", ru: "Бирка" }, fields: ["field_number", "name", "ex"] }],
};

export function plant(
  row: number,
  tag: string | null,
  fields: Record<string, string>,
  custom: Record<string, string> = {},
  invalid: Plant["invalid"] = {},
): Plant {
  return { id: `main:${String(row)}`, collection_id: "main", tag, row, fields, custom, invalid };
}
