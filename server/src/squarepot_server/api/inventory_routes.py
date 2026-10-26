# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP routes for the inventory: sightings and the plants not seen (ADR 0008)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select

from squarepot_server.api.models import Plant, SightingBatch, SightingResult
from squarepot_server.api.routes import RuntimeDep, SessionDep, errors, require_token, to_plants
from squarepot_server.db import CollectionRow, PlantRow
from squarepot_server.fields import STATUS

router = APIRouter(
    prefix="/api/v1",
    tags=["inventory"],
    dependencies=[Depends(require_token)],
    responses=errors(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_429_TOO_MANY_REQUESTS,
    ),
)


@router.post(
    "/sightings",
    summary="Record that plants were seen",
    description=(
        "For the phone's queue of sightings, sent when it is online. Each sighting has an id "
        "the client chose, so sending a batch again records nothing twice. A sighting of a "
        "number no plant has is not recorded; the server reads the sheet again first, at "
        "most once a minute, in case the plant was just added there. The plants seen are "
        "sent again in the next sync, with their new `last_seen`. Without a photo storage "
        "the server keeps no sightings and answers 503."
    ),
    responses=errors(status.HTTP_503_SERVICE_UNAVAILABLE),
)
def record_sightings(body: SightingBatch, runtime: RuntimeDep) -> list[SightingResult]:
    if runtime.sightings is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Sightings need the photo storage, which is not set up on this server.",
        )
    outcomes = runtime.sightings.record(body.sightings)
    return [
        SightingResult(id=sighting.id, result=outcome)
        for sighting, outcome in zip(body.sightings, outcomes, strict=True)
    ]


def before(day: date | None, moment: datetime | None) -> bool:
    """Whether `moment` is before the start of `day`, in UTC; never is before any day."""
    if day is None:
        return True
    return moment is None or moment < datetime.combine(day, time(), tzinfo=UTC)


@router.get(
    "/collections/{collection_id}/plants",
    summary="List a collection's plants, filtered for an inventory",
    description=(
        "Every plant of the collection, in sheet order, that matches all the filters given. "
        "Former plants, those with a `status`, are left out unless `former` is true. The "
        "apps filter their own copies the same way; this is for the bot and for scripts."
    ),
    responses=errors(status.HTTP_404_NOT_FOUND),
)
def list_plants(
    collection_id: Annotated[str, Path(examples=["main"])],
    session: SessionDep,
    seen_before: Annotated[
        date | None,
        Query(description="Only plants not seen since this day (UTC), never seen included."),
    ] = None,
    photo_before: Annotated[
        date | None,
        Query(description="Only plants with no photo taken since this day, none included."),
    ] = None,
    has_photo: Annotated[
        bool | None, Query(description="Only plants with photos, or only those without.")
    ] = None,
    former: Annotated[bool, Query(description="Include former plants.")] = False,
) -> list[Plant]:
    collection = session.get(CollectionRow, collection_id)
    if collection is None or collection.removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No collection {collection_id!r}.")
    rows = session.scalars(
        select(PlantRow)
        .where(PlantRow.collection_id == collection_id, ~PlantRow.removed)
        .order_by(PlantRow.row, PlantRow.id)
    ).all()
    return [
        plant
        for plant in to_plants(session, rows)
        if (former or STATUS not in plant.fields)
        and before(seen_before, plant.last_seen)
        and before(photo_before, plant.last_photo)
        and (has_photo is None or (plant.photo_count > 0) == has_photo)
    ]
