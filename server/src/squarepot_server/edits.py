# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adding and editing plants by writing cells to the sheet (ADR 0006).

The sheet wins. An edit names the value it saw in each cell it changes; the
tab is read again before anything is written, and if one of those cells has
changed, nothing is. After a write the copy is read again from the sheet, so
it holds the edit as the sheet has it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from squarepot_server.api.models import FieldChange, FieldDefinition, FieldType, NewPlant, PlantEdit
from squarepot_server.config import CollectionConfig
from squarepot_server.db import PlantRow, RegisteredTag
from squarepot_server.fields import (
    MAX_CUSTOM_VALUE,
    TAG,
    InvalidValue,
    Row,
    TabError,
    custom_header,
    map_header,
    parse_tab,
    read_value,
)
from squarepot_server.store import CellWrite, EditableStore
from squarepot_server.sync import Syncer

log = logging.getLogger(__name__)
LAST_NUMBER = 999_999


class NotFound(Exception):
    """No such plant or collection."""


class NotEditable(Exception):
    """The collection is not read with the service account."""


class InvalidEdit(Exception):
    """Values that would not read back as themselves, or columns the sheet lacks."""


class Conflict(Exception):
    """The sheet no longer holds what the client saw; nothing was written."""

    def __init__(self, message: str, plant: PlantRow | None) -> None:
        super().__init__(message)
        self.plant = plant


@dataclass(frozen=True)
class Tab:
    rows: list[Row]
    # Column index by field key, and by custom column name.
    fields: dict[str, int]
    custom: dict[str, int]


@dataclass(frozen=True)
class Change:
    """A checked change to one cell: a field when `definition` is set, else a custom column."""

    name: str
    definition: FieldDefinition | None
    seen: str | None
    value: str | Decimal | date | None


def written_value(
    definition: FieldDefinition | None, value: str | None
) -> str | Decimal | date | None:
    """The value to write, or None to empty the cell.

    Raises InvalidValue unless the value would read back from the sheet as itself.
    """
    if value is None or not value.strip():
        if definition is not None and definition.required:
            raise InvalidValue("is required")
        return None
    if definition is None:
        if len(value) > MAX_CUSTOM_VALUE:
            raise InvalidValue(f"is longer than {MAX_CUSTOM_VALUE} characters")
        read = value.strip()
    else:
        read = read_value(definition, value)
    if read != value:
        raise InvalidValue(f"write it as {read!r}")
    if definition is not None and definition.type == FieldType.DATE:
        return date.fromisoformat(value)
    if definition is not None and definition.type == FieldType.DECIMAL:
        return Decimal(value)
    return value


class Editor:
    def __init__(self, syncer: Syncer) -> None:
        self.syncer = syncer

    def editable(self) -> bool:
        return isinstance(self.syncer.store, EditableStore)

    def store(self) -> EditableStore:
        store = self.syncer.store
        if not isinstance(store, EditableStore):
            raise NotEditable(
                "Plants can only be edited in a collection read with the service account."
            )
        return store

    def config(self, collection_id: str) -> CollectionConfig:
        for collection in self.syncer.collections:
            if collection.id == collection_id:
                return collection
        raise NotFound(f"No collection {collection_id!r}.")

    def changes(
        self, fields: dict[str, FieldChange], custom: dict[str, FieldChange]
    ) -> list[Change]:
        """Check the new values against the schema; raises InvalidEdit naming every problem."""
        definitions = {definition.key: definition for definition in self.syncer.schema.fields}
        problems = []
        result = []
        for key, change in fields.items():
            definition = definitions.get(key)
            if key == TAG:
                problems.append("tag: numbers are issued by the server, ask for issue_number")
            elif definition is None:
                problems.append(f"{key}: no such field")
            else:
                try:
                    value = written_value(definition, change.value)
                except InvalidValue as error:
                    problems.append(f"{key}: {error}")
                else:
                    result.append(Change(key, definition, change.seen, value))
        for name, change in custom.items():
            try:
                value = written_value(None, change.value)
            except InvalidValue as error:
                problems.append(f"{name}: {error}")
            else:
                result.append(Change(name, None, change.seen, value))
        if problems:
            raise InvalidEdit("; ".join(problems))
        return result

    def read(self, store: EditableStore, collection: CollectionConfig) -> Tab:
        values = store.read(collection)
        try:
            parsed = parse_tab(self.syncer.schema, values)
            columns = map_header(self.syncer.schema, values[0])
        except TabError as error:
            raise Conflict(f"The sheet cannot be read: {error}.", None) from error
        custom, _ = custom_header(self.syncer.schema, values[0])
        return Tab(
            parsed.rows,
            {definition.key: index for index, definition in columns.items()},
            {name: index for index, name in custom.items()},
        )

    @staticmethod
    def cells(tab: Tab, changes: list[Change], number: bool) -> list[CellWrite]:
        """Where each change goes; raises InvalidEdit for columns the sheet lacks."""
        problems = []
        cells = []
        for change in changes:
            columns = tab.fields if change.definition is not None else tab.custom
            if change.name in columns:
                cells.append(CellWrite(columns[change.name], change.value))
            elif change.definition is not None:
                problems.append(f"{change.name}: the sheet has no '{change.name}' column, add one")
            else:
                problems.append(f"{change.name}: the sheet has no custom column of that name")
        if number and TAG not in tab.fields:
            problems.append("tag: the sheet has no 'tag' column, add one")
        if problems:
            raise InvalidEdit("; ".join(problems))
        return cells

    def issue_number(self, collection_id: str) -> str:
        """Take the next free number and record it before it is written (ADR 0002)."""
        with self.syncer.sessions.begin() as session:
            highest = session.scalar(select(func.max(RegisteredTag.tag)))
            number = int(highest or 0) + 1
            if number > LAST_NUMBER:
                raise InvalidEdit("tag: every number from 000001 to 999999 is taken")
            tag = f"{number:06d}"
            session.add(
                RegisteredTag(
                    tag=tag, collection_id=collection_id, registered_at=self.syncer.clock()
                )
            )
        return tag

    def plant(self, plant_id: str) -> PlantRow:
        with self.syncer.sessions.begin() as session:
            plant = session.get(PlantRow, plant_id)
        if plant is None or plant.removed:
            raise NotFound(f"No plant {plant_id!r}.")
        return plant

    def find(self, collection_id: str, tag: str | None, row: int) -> PlantRow | None:
        """The plant with this number, or the one without a number in this row."""
        query = select(PlantRow).where(PlantRow.collection_id == collection_id, ~PlantRow.removed)
        if tag is not None:
            query = query.where(PlantRow.tag == tag)
        else:
            query = query.where(PlantRow.tag.is_(None), PlantRow.row == row)
        with self.syncer.sessions.begin() as session:
            plants = session.scalars(query).all()
        if len(plants) > 1:
            # An unresolved collision of numbers (ADR 0002): the row tells them apart.
            plants = [plant for plant in plants if plant.row == row]
        return plants[0] if len(plants) == 1 else None

    def found(self, collection_id: str, tag: str | None, row: int) -> PlantRow:
        plant = self.find(collection_id, tag, row)
        if plant is None:
            raise Conflict(
                "Written, but the row can no longer be found in the copy: sync to see it.", None
            )
        return plant

    def conflict(self, collection: CollectionConfig, plant: PlantRow, message: str) -> Conflict:
        """A conflict carrying the plant as the sheet now has it."""
        self.syncer.sync_collection(collection, force=True)
        if plant.tag is not None:
            current = self.find(collection.id, plant.tag, plant.row)
        else:
            with self.syncer.sessions.begin() as session:
                current = session.get(PlantRow, plant.id)
            if current is not None and current.removed:
                current = None
        return Conflict(message, current)

    def edit(self, plant_id: str, edit: PlantEdit) -> PlantRow:
        with self.syncer.lock:
            plant = self.plant(plant_id)
            collection = self.config(plant.collection_id)
            store = self.store()
            changes = self.changes(edit.fields, edit.custom)
            tab = self.read(store, collection)
            number = edit.issue_number and plant.tag is None
            cells = self.cells(tab, changes, number)
            row = self.row(tab, plant)
            if row is None:
                raise self.conflict(
                    collection, plant, "The plant's row is no longer in the sheet as it was."
                )
            changed = [change.name for change in changes if current(row, change) != change.seen]
            if changed:
                raise self.conflict(
                    collection, plant, f"Changed in the sheet since: {', '.join(changed)}."
                )
            tag = row.tag
            if number:
                if TAG in row.invalid:
                    raise self.conflict(
                        collection, plant, "The tag cell holds something that is not a number."
                    )
                tag = self.issue_number(collection.id)
                cells.append(CellWrite(tab.fields[TAG], tag, number=True))
            if cells:
                store.write(collection, row.row, cells)
                log.info("plant %s: wrote %s", plant.id, written(changes, tag != row.tag))
                self.syncer.sync_collection(collection, force=True)
            return self.found(collection.id, tag, row.row)

    def create(self, collection_id: str, new: NewPlant) -> PlantRow:
        with self.syncer.lock:
            collection = self.config(collection_id)
            store = self.store()
            given = {key: FieldChange(seen=None, value=value) for key, value in new.fields.items()}
            for definition in self.syncer.schema.fields:
                if definition.required and definition.key not in given:
                    given[definition.key] = FieldChange(seen=None, value=None)
            custom = {
                name: FieldChange(seen=None, value=value) for name, value in new.custom.items()
            }
            changes = [change for change in self.changes(given, custom) if change.value is not None]
            tab = self.read(store, collection)
            cells = self.cells(tab, changes, new.issue_number)
            tag = None
            if new.issue_number:
                tag = self.issue_number(collection.id)
                cells.append(CellWrite(tab.fields[TAG], tag, number=True))
            row = store.append(collection, cells)
            log.info(
                "collection %s: added row %d with %s",
                collection.id,
                row,
                written(changes, tag is not None),
            )
            self.syncer.sync_collection(collection, force=True)
            return self.found(collection.id, tag, row)

    @staticmethod
    def row(tab: Tab, plant: PlantRow) -> Row | None:
        """The plant's row in the tab just read: by its number, or else by its place and cells."""
        if plant.tag is not None:
            rows = [row for row in tab.rows if row.tag == plant.tag]
            if len(rows) > 1:
                rows = [row for row in rows if row.row == plant.row]
        else:
            rows = [
                row
                for row in tab.rows
                if row.tag is None
                and row.row == plant.row
                and row.fields == plant.fields
                and row.custom == plant.custom
            ]
        return rows[0] if len(rows) == 1 else None


def current(row: Row, change: Change) -> str | None:
    """What the client should have seen in the cell: as `Plant` shows it."""
    if change.definition is None:
        return row.custom.get(change.name)
    if change.name in row.invalid:
        return row.invalid[change.name]["value"]
    return row.fields.get(change.name)


def written(changes: list[Change], number: bool) -> str:
    """The fields written, for the log: keys only, never values or custom column names."""
    keys = [change.name for change in changes if change.definition is not None]
    keys += [TAG] if number else []
    customs = sum(change.definition is None for change in changes)
    if customs:
        keys.append(f"{customs} custom")
    return ", ".join(keys) or "nothing"
