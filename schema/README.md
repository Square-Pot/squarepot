# Schema

The single, machine-readable definition of the plant fields. Every other
component follows what is defined here, and changes start in this directory.

- [`fields.yaml`](fields.yaml): the fields, their types, labels in each UI
  language, display rules and the default presets.
- [`fields.schema.json`](fields.schema.json): the JSON Schema that `fields.yaml`
  is validated against in pre-commit and CI.

How the fields map onto a Google Sheet is described in
[`docs/sheet-format.md`](../docs/sheet-format.md). The server's OpenAPI contract
will be published here as well.
