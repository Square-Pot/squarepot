# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request and response bodies of the HTTP API.

These models are the API contract: `openapi.json` is generated from them, and
the Android app, the bot and the web app are built against that file.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

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


class LabelLayout(ApiModel):
    """Label size and sheet layout. Lengths are in millimetres."""

    width_mm: float = Field(gt=0, le=300, description="Label width.")
    height_mm: float = Field(gt=0, le=300, description="Label height.")
    module_mm: float = Field(
        ge=0.5,
        le=5,
        description=(
            "Size of one module of the code. The symbol is 10 modules wide, and a white quiet "
            "zone of at least one module surrounds it on the label."
        ),
    )
    max_lines: int = Field(
        ge=0, le=20, description="Most caption lines under the code; `0` prints the code only."
    )
    caption_box: bool = Field(description="Draw a frame around the caption.")
    show_number: bool = Field(
        description="Print the six-digit number as the caption's first line; needs `max_lines`."
    )
    page: PageSize
    margin_mm: float = Field(
        ge=0,
        le=50,
        description=(
            "Blank margin on every side of the page. Most printers cannot print the outer "
            "3-5 mm, so a smaller margin can cut off the outer labels. Print at 100 %."
        ),
    )
    gap_mm: float = Field(ge=0, le=50, description="Space between labels, where they are cut.")
    cut_lines: bool = Field(
        description="Draw thin grey cutting lines in the gaps; needs `gap_mm` of 0.1 or more."
    )


class LabelLayoutOverrides(ApiModel):
    """Values that replace those of the template; omitted ones keep the template's."""

    width_mm: float | None = Field(default=None, gt=0, le=300)
    height_mm: float | None = Field(default=None, gt=0, le=300)
    module_mm: float | None = Field(default=None, ge=0.5, le=5)
    max_lines: int | None = Field(default=None, ge=0, le=20)
    caption_box: bool | None = None
    show_number: bool | None = None
    page: PageSize | None = None
    margin_mm: float | None = Field(default=None, ge=0, le=50)
    gap_mm: float | None = Field(default=None, ge=0, le=50)
    cut_lines: bool | None = None


class LabelTemplate(ApiModel):
    key: Key = Field(examples=["strip"])
    label: Label
    description: str
    layout: LabelLayout


class LabelRequest(ApiModel):
    plants: list[str] = Field(
        min_length=1,
        max_length=2000,
        description="Ids of the plants to label, in print order. Every plant must have a tag.",
    )
    template: Key = Field(
        default="strip", description="Key of a template from `/labels/templates`."
    )
    preset: Key = Field(default="label", description="Key of the preset that makes the caption.")
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
