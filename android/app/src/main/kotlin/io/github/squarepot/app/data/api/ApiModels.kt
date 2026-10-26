// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

// Models of the server's v1 API, as declared in server/openapi.json. Unknown keys are ignored
// and enum-like values that may grow (field types, groups, display case) are kept as strings,
// so an additive change on the server does not break an installed app.

/** Shared JSON settings for the API and for what the app stores from it. */
val ApiJson = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
}

@Serializable
enum class SyncKind {
    @SerialName("full")
    FULL,

    @SerialName("delta")
    DELTA,
}

/** `GET /api/v1/sync`: a full copy, or the changes since a cursor. */
@Serializable
data class SyncResponse(
    val kind: SyncKind,
    val cursor: String,
    @SerialName("schema_version") val schemaVersion: Int,
    val collections: List<CollectionDto>,
    @SerialName("removed_collections") val removedCollections: List<String>,
    val plants: List<PlantDto>,
    @SerialName("removed_plants") val removedPlants: List<String>,
)

@Serializable
data class CollectionDto(
    val id: String,
    val name: String,
    @SerialName("plant_count") val plantCount: Int,
    /** When the server last read the sheet successfully (ISO 8601), or null before the first read. */
    @SerialName("synced_at") val syncedAt: String? = null,
    /** Why the server's last read of the sheet failed, in English; null when it succeeded. */
    val error: String? = null,
    /** The sheet's own columns, which are not schema fields, in column order. */
    @SerialName("custom_columns") val customColumns: List<String> = emptyList(),
    /** Whether plants can be edited through the API: only collections read with the service account (ADR 0006). */
    val editable: Boolean = false,
)

@Serializable
data class PlantDto(
    val id: String,
    @SerialName("collection_id") val collectionId: String,
    /** Six-digit number with leading zeros; null when the plant has no label yet. */
    val tag: String? = null,
    val row: Int,
    /** Canonical field values by schema key; empty cells are absent. */
    val fields: Map<String, String> = emptyMap(),
    /** Values of the collection's custom columns by name, as the sheet shows them; empty cells are absent. */
    val custom: Map<String, String> = emptyMap(),
    /** Since when the plant has its status (YYYY-MM-DD); null without a status. */
    @SerialName("status_since") val statusSince: String? = null,
    /** When the plant was last seen (ISO 8601): its newest sighting or photo; null when never seen. */
    @SerialName("last_seen") val lastSeen: String? = null,
    @SerialName("photo_count") val photoCount: Int = 0,
    /** When the newest photo was taken (ISO 8601); null without photos. */
    @SerialName("last_photo") val lastPhoto: String? = null,
    /** The photo to show for the plant: the owner's choice, else the newest. */
    @SerialName("main_photo_id") val mainPhotoId: String? = null,
)

/** `GET /api/v1/schema`: schema/fields.yaml as JSON. */
@Serializable
data class FieldSchemaDto(
    val version: Int,
    val fields: List<FieldDefinitionDto>,
    val computed: List<ComputedFieldDto> = emptyList(),
    val presets: List<PresetDto> = emptyList(),
)

@Serializable
data class FieldDefinitionDto(
    val key: String,
    /** text, date or decimal in schema version 1. */
    val type: String,
    val label: LabelDto,
    val group: String,
    val description: String? = null,
    val aliases: List<String> = emptyList(),
    val required: Boolean = false,
    val pattern: String? = null,
    val display: DisplayDto? = null,
)

@Serializable
data class DisplayDto(
    val prefix: String? = null,
    val italic: Boolean = false,
    val quote: Boolean = false,
    val case: String = "as-is",
)

@Serializable
data class ComputedFieldDto(
    val key: String,
    val label: LabelDto,
    val from: List<String>,
    val description: String? = null,
)

@Serializable
data class PresetDto(val key: String, val label: LabelDto, val fields: List<String>)

@Serializable
data class LabelDto(val en: String, val ru: String) {
    /** The label in [language] (an ISO 639 code), English when there is none. */
    fun forLanguage(language: String): String = if (language == "ru") ru else en
}

/** How a plant was seen without a photo (ADR 0008); a photo is a sighting by itself. */
@Serializable
enum class SightingKind {
    /** Marked as seen without a photo. */
    @SerialName("seen")
    SEEN,

    /** Its status was set. */
    @SerialName("status")
    STATUS,
}

/** One sighting for `POST /api/v1/sightings`; [id] is the client's, so a resend records nothing twice. */
@Serializable
data class SightingDto(
    val id: String,
    val tag: String,
    @SerialName("seen_at") val seenAt: String,
    val kind: SightingKind,
)

@Serializable
data class SightingBatchDto(val sightings: List<SightingDto>)

/** What the server did with a sighting: recorded, already_recorded or unknown_number. */
@Serializable
data class SightingResultDto(val id: String, val result: String)

/** A photo as the server keeps it; only what the phone needs. */
@Serializable
data class PhotoDto(
    val id: String,
    val tag: String,
    @SerialName("taken_at") val takenAt: String,
    val comment: String? = null,
)

/** `PATCH /api/v1/photos/{id}`: an empty [comment] removes it. */
@Serializable
data class PhotoChangeDto(val comment: String)

/** The body of every error response. */
@Serializable
data class ErrorDto(val code: String, val message: String)
