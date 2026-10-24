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

/** The body of every error response. */
@Serializable
data class ErrorDto(val code: String, val message: String)
