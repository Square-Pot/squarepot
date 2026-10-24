# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request and response bodies of the HTTP API.

These models are the API contract: `openapi.json` is generated from them, and
the Android app, the bot and the web app are built against that file.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Tag = Annotated[
    str,
    Field(
        pattern=r"^(?!000000)[0-9]{6}$",
        description='Six-digit plant number with leading zeros, as on the label: "004217".',
        examples=["004217"],
    ),
]


class ApiModel(BaseModel):
    # The Python engine supports the look-ahead in the tag pattern of schema/fields.yaml.
    model_config = ConfigDict(extra="forbid", regex_engine="python-re")


class Error(ApiModel):
    """The body of every error response."""

    code: str = Field(
        description="Stable, machine-readable error code, such as `not_found`.",
        examples=["not_found"],
    )
    message: str = Field(description="Human-readable explanation, in English.")


class Health(ApiModel):
    status: str = Field(description="Always `ok` when the server answers.", examples=["ok"])
    version: str = Field(description="Server version.", examples=["0.1.0"])


Key = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$", examples=["genus"])]


class Label(ApiModel):
    """A name in each UI language."""

    en: str = Field(min_length=1)
    ru: str = Field(min_length=1)


class FieldType(StrEnum):
    TEXT = "text"
    DATE = "date"
    DECIMAL = "decimal"


class FieldGroup(StrEnum):
    BASIC = "basic"
    EXTRA = "extra"


class Display(ApiModel):
    """How a field renders inside a plant name or caption."""

    prefix: str | None = Field(
        default=None, description='Text before the value ("subsp."), never italic.'
    )
    italic: bool = Field(default=False, description="Render the value in italics.")
    quote: bool = Field(default=False, description="Wrap the value in single curly quotes.")
    case: Literal["lower", "title", "upper", "as-is"] = Field(
        default="as-is", description="Case normalisation, for display only."
    )


class FieldDefinition(ApiModel):
    key: Key = Field(description="Column header in the sheet and key in `Plant.fields`.")
    type: FieldType
    label: Label
    description: str | None = None
    aliases: list[Key] = Field(default=[], description="Other headers accepted on read.")
    required: bool = False
    group: FieldGroup
    pattern: str | None = Field(default=None, description="Regular expression a value matches.")
    display: Display = Field(default_factory=Display)


class ComputedField(ApiModel):
    model_config = ConfigDict(serialize_by_alias=True)

    key: Key
    label: Label
    description: str | None = None
    from_: list[Key] = Field(
        alias="from", min_length=1, description="Fields the value is derived from."
    )


class Preset(ApiModel):
    key: Key
    label: Label
    fields: list[Key] = Field(
        min_length=1, description="Field and computed field keys, in display order."
    )


class FieldSchema(ApiModel):
    """The field schema, `schema/fields.yaml` as JSON.

    Clients keep it with their local copy and fetch it again when
    `Sync.schema_version` differs from its `version`.
    """

    version: int = Field(ge=1)
    fields: list[FieldDefinition] = Field(min_length=1)
    computed: list[ComputedField]
    presets: list[Preset] = Field(
        description="The built-in presets. Presets defined by the owner will be listed here too."
    )


class InvalidCell(ApiModel):
    """A cell the import rejected, for showing to the owner."""

    cell: str = Field(description="Where it is in the sheet, such as `F12`.", examples=["F12"])
    value: str = Field(
        description="What the cell held, as text; cut short with `…` beyond 200 characters.",
        examples=["March 2024"],
    )
    reason: str = Field(description="Why it was rejected.", examples=["not a date (YYYY-MM-DD)"])


class Collection(ApiModel):
    """One collection: one tab of a Google Sheet."""

    id: str = Field(description="Opaque, stable collection id.", examples=["main"])
    name: str = Field(description="Display name chosen by the owner.", examples=["Lithops"])
    plant_count: int = Field(ge=0, description="Number of imported plants.")
    synced_at: AwareDatetime | None = Field(
        description=(
            "When the server last confirmed that its copy matches the sheet: the last "
            "successful check, whether or not the sheet had changed. `null` before the first."
        ),
    )
    error: str | None = Field(
        description=(
            "Why the last sync attempt failed, such as an unreachable sheet or a missing "
            "`genus` column. `null` when it succeeded. The server keeps serving its last copy."
        ),
    )
    custom_columns: list[str] = Field(
        description=(
            "Names of the tab's custom columns, in column order: the columns whose header is "
            "not a field key or alias. A client may let the owner choose which to show."
        ),
        examples=[["Marathon", "soil"]],
    )
    sheet_url: str | None = Field(
        description=(
            "Address of the collection's sheet in Google Sheets, opening its tab when the "
            "server knows the tab's `gid`, and the first tab otherwise. To open a plant's row, "
            "add `range=A<row>` to the fragment: `#range=A12`, or `&range=A12` when the "
            "address already has a `#`. `null` for a collection read from a file."
        ),
        examples=["https://docs.google.com/spreadsheets/d/1AbC/edit#gid=0"],
    )


class Plant(ApiModel):
    """One plant: one row of a collection's tab."""

    id: str = Field(
        description=(
            "Opaque plant id, stable across syncs while the row can be matched. Clients "
            "must not parse it. A tag is not an id: rows without a tag have one too."
        ),
    )
    collection_id: str = Field(description="Id of the collection the plant belongs to.")
    tag: Tag | None = Field(description="Plant number; `null` when the plant has no label yet.")
    row: int = Field(ge=2, description="Row number in the sheet, for showing to the owner.")
    fields: dict[str, str] = Field(
        description=(
            "Field values by key from `schema/fields.yaml`, except `tag`, which is in "
            "`Plant.tag`. Empty and invalid cells are omitted. Values are in canonical form: "
            "`text` trimmed, `date` as `YYYY-MM-DD`, `decimal` as a plain decimal string such "
            "as `12.50`. Computed fields (`name`, `age`) are not included; clients render them "
            "by the schema's rules."
        ),
        examples=[{"genus": "Lithops", "species": "lesliei", "seeding_date": "2024-03-15"}],
    )
    custom: dict[str, str] = Field(
        description=(
            "Values of the collection's `custom_columns` by name, as text, as the sheet shows "
            "them. Empty cells are omitted."
        ),
        examples=[{"Marathon": "yes", "soil": "pumice 70%"}],
    )
    invalid: dict[str, InvalidCell] = Field(
        description=(
            "Cells of this row the import rejected, by field key, such as a `seeding_date` "
            "that is not a date. The field is then missing from `fields`, or `tag` is `null`."
        ),
        examples=[
            {
                "seeding_date": {
                    "cell": "F12",
                    "value": "March 2024",
                    "reason": "not a date (YYYY-MM-DD)",
                }
            }
        ],
    )


class TagLookup(ApiModel):
    tag: Tag
    plants: list[Plant] = Field(
        min_length=1,
        description=(
            "Every plant with this number. Numbers are unique, so this holds one plant, "
            "except while an import collision is unresolved (ADR 0002)."
        ),
    )


class SyncKind(StrEnum):
    FULL = "full"
    DELTA = "delta"


class Sync(ApiModel):
    """A batch of changes to the client's local copy of every collection (ADR 0005)."""

    kind: SyncKind = Field(
        description=(
            "`full`: the response holds every collection and plant, and the client replaces "
            "its whole copy with it. `delta`: it holds only what changed since the cursor, "
            "and the client applies it to its copy. The server answers with `full` when no "
            "cursor was sent, the cursor is malformed, unknown or too old, or the schema "
            "version has changed since it was issued."
        ),
    )
    cursor: str = Field(
        description="Opaque cursor to send with the next sync. Clients must not parse it.",
    )
    schema_version: int = Field(
        ge=1,
        description="`version` of `schema/fields.yaml` that the field keys follow.",
    )
    collections: list[Collection] = Field(
        description=(
            "Collections that are new or changed (`delta`), or all of them (`full`). A change "
            "of `synced_at` or `error` alone counts as a change."
        ),
    )
    removed_collections: list[str] = Field(
        description=(
            "Ids of collections removed since the cursor. Their plants are listed in "
            "`removed_plants` too. Always empty in `full`."
        ),
    )
    plants: list[Plant] = Field(
        description="Plants that are new or changed (`delta`), or all of them (`full`).",
    )
    removed_plants: list[str] = Field(
        description="Ids of plants removed since the cursor. Always empty in `full`.",
    )


class PageSize(StrEnum):
    A4 = "a4"
    LETTER = "letter"


class LabelFormat(StrEnum):
    PDF = "pdf"
    SVG = "svg"


class LabelLanguage(StrEnum):
    EN = "en"
    RU = "ru"


class LabelOrientation(StrEnum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


# Most printers cannot print the outer 3-5 mm of a sheet.
MIN_MARGIN_MM = 5
# The template that picks each plant's template from its `label_type`.
AUTO_TEMPLATE = "auto"


class LabelLayout(ApiModel):
    """Label size and sheet layout. Lengths are in millimetres."""

    orientation: LabelOrientation = Field(
        description=(
            "`vertical`: the code on top and the caption under it. `horizontal`: the caption "
            "on the left and the code on the right."
        )
    )
    width_mm: float = Field(gt=0, le=300, description="Label width.")
    height_mm: float = Field(gt=0, le=300, description="Label height, burial zone included.")
    burial_mm: float = Field(
        ge=0,
        le=300,
        description=(
            "Height of the white zone at the bottom of the label that goes into the substrate. "
            "A dashed grey line marks the soil level."
        ),
    )
    band_mm: float = Field(
        ge=0,
        le=50,
        description=(
            "Height of a blank band between the code and the burial zone. It lifts the code "
            "clear of the soil and stones, and may itself go into the substrate. Needs "
            "`burial_mm`."
        ),
    )
    chamfer_mm: float = Field(
        ge=0,
        le=50,
        description=(
            "How far the burial zone's bottom corners are cut in, so that the label goes into "
            "the substrate easily; drawn as grey cutting lines. Needs `burial_mm`."
        ),
    )
    burial_text: bool = Field(
        description=(
            "Print the request's `burial_preset` in the burial zone, clear of the cut corners: "
            "each field on its own line with its label in bold, shrunk and then cut short to fit."
        )
    )
    module_mm: float = Field(
        ge=0.5,
        le=5,
        description=(
            "Size of one module of the code. The symbol is 10 modules wide, and a white quiet "
            "zone of at least one module surrounds it on the label."
        ),
    )
    max_lines: int = Field(
        ge=0, le=20, description="Most caption lines beside the code; `0` prints the code only."
    )
    caption_box: bool = Field(description="Draw a frame around the caption.")
    show_number: bool = Field(
        description=(
            "Print the six-digit number, a backup for the code, small next to it: under the "
            "code on a vertical label, down its side on a horizontal one. It is never part of "
            "the caption."
        )
    )
    page: PageSize
    margin_mm: float = Field(
        ge=MIN_MARGIN_MM,
        le=50,
        description=(
            "Blank margin on every side of the page, at least 5 mm: most printers cannot "
            "print the outer 3-5 mm. Print at 100 %."
        ),
    )
    gap_mm: float = Field(ge=0, le=50, description="Space between labels, where they are cut.")
    cut_lines: bool = Field(
        description="Draw thin grey cutting lines in the gaps; needs `gap_mm` of 0.1 or more."
    )


class LabelLayoutOverrides(ApiModel):
    """Values that replace those of the template; omitted ones keep the template's."""

    orientation: LabelOrientation | None = None
    width_mm: float | None = Field(default=None, gt=0, le=300)
    height_mm: float | None = Field(default=None, gt=0, le=300)
    burial_mm: float | None = Field(default=None, ge=0, le=300)
    band_mm: float | None = Field(default=None, ge=0, le=50)
    chamfer_mm: float | None = Field(default=None, ge=0, le=50)
    burial_text: bool | None = None
    module_mm: float | None = Field(default=None, ge=0.5, le=5)
    max_lines: int | None = Field(default=None, ge=0, le=20)
    caption_box: bool | None = None
    show_number: bool | None = None
    page: PageSize | None = None
    margin_mm: float | None = Field(default=None, ge=MIN_MARGIN_MM, le=50)
    gap_mm: float | None = Field(default=None, ge=0, le=50)
    cut_lines: bool | None = None


class LabelTemplate(ApiModel):
    key: Key = Field(examples=["vertical"])
    label: Label
    description: str
    layout: LabelLayout


class LabelEntry(ApiModel):
    """One thing to print on a label: a schema field, or a custom column."""

    field: Key | None = Field(
        default=None,
        description="Key of a field from `/schema`, or the computed `name` in a caption.",
    )
    custom: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description=(
            "Name of a custom column from `Collection.custom_columns`, printed as "
            "`Name: value`. A plant without a value for it prints nothing for it."
        ),
    )

    @model_validator(mode="after")
    def one_of(self) -> LabelEntry:
        if (self.field is None) == (self.custom is None):
            raise ValueError("give either `field` or `custom`")
        return self


class LabelRequest(ApiModel):
    plants: list[str] = Field(
        min_length=1,
        max_length=2000,
        description="Ids of the plants to label, in print order. Every plant must have a tag.",
    )
    template: Key = Field(
        default=AUTO_TEMPLATE,
        description=(
            "Key of a template from `/labels/templates`, or `auto`: each plant gets the "
            "`horizontal` template when its `label_type` is `h`, and the `vertical` one "
            "otherwise. Each template's labels start on a page of their own, vertical first, "
            "and `layout` applies to both."
        ),
    )
    preset: Key = Field(default="label", description="Key of the preset that makes the caption.")
    burial_preset: Key | None = Field(
        default="burial",
        description=(
            "Key of the preset printed in the burial zone of a template with `burial_text`; "
            "`null` leaves the zone blank."
        ),
    )
    caption_fields: list[LabelEntry] | None = Field(
        default=None,
        max_length=30,
        description=(
            "What the caption shows, in order, instead of `preset`'s fields. The plant's "
            "`name` is always included: first, when the list leaves it out."
        ),
    )
    extra_fields: list[LabelEntry] | None = Field(
        default=None,
        max_length=30,
        description=(
            "More about the plant, in order, each as `Label: value`: in the burial zone of a "
            "template with `burial_text`, instead of `burial_preset`'s fields, and after the "
            "caption on other templates, where it is cut first when space runs out. Omitted: "
            "`burial_preset` in the burial zone, and nothing after a caption."
        ),
    )
    language: LabelLanguage = Field(
        default=LabelLanguage.EN,
        description="Language of the field labels in the burial zone and in `extra_fields`.",
    )
    layout: LabelLayoutOverrides = Field(default_factory=LabelLayoutOverrides)
    format: LabelFormat = LabelFormat.PDF
    page: int = Field(
        default=1,
        ge=1,
        description=(
            "Page to return as SVG, which holds one page; ignored for PDF, which holds them all. "
            "The page count is in the `X-Page-Count` response header."
        ),
    )
    skip: int = Field(
        default=0,
        ge=0,
        le=1000,
        description=(
            "Label positions to leave empty at the start, to reuse a partly used sheet; "
            "fewer than a page holds."
        ),
    )
