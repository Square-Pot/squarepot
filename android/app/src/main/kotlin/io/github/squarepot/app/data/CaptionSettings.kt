// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import io.github.squarepot.app.data.api.ApiJson
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.SerializationException
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer

/** Where the camera shows the selected label's caption. */
enum class CaptionPlace {
    /** Next to the label's number; no bottom panel. */
    LABEL,

    /** In the dark panel at the bottom, as before. */
    PANEL,
}

/** How a caption at the label looks. */
enum class CaptionLook {
    /** A paper card hanging off the number tab. */
    CARD,

    /** Text with a dark halo, straight on the picture. */
    BARE,
}

/** What neighbouring labels show besides their frame. */
enum class NeighbourNames {
    NUMBER_ONLY,

    /** The number and a short name ("M. theresae"). */
    SHORT_NAME,
}

/**
 * How the camera captions labels, kept on the phone. [fields] is null until the owner changes the
 * list: captions then show [defaultCaptionFields] for the copy's current custom columns.
 */
data class CaptionSettings(
    val place: CaptionPlace = CaptionPlace.LABEL,
    val look: CaptionLook = CaptionLook.CARD,
    val fields: List<CaptionField>? = null,
    val nameMode: NameMode = NameMode.FULL,
    val neighbours: NeighbourNames = NeighbourNames.NUMBER_ONLY,
    /** The bottom panel folded to one line. */
    val panelFolded: Boolean = false,
) {
    /** The fields a caption shows, given the collections' [customColumns] in order. */
    fun fieldsFor(customColumns: List<String>): List<CaptionField> = fields ?: defaultCaptionFields(customColumns)
}

class CaptionSettingsStore(private val dataStore: DataStore<Preferences>) {
    val settings: Flow<CaptionSettings> = dataStore.data.map {
        CaptionSettings(
            place = enumOr(it[PLACE], CaptionPlace.LABEL),
            look = enumOr(it[LOOK], CaptionLook.CARD),
            fields = it[FIELDS]?.let(::decodeCaptionFields),
            nameMode = enumOr(it[NAME_MODE], NameMode.FULL),
            neighbours = enumOr(it[NEIGHBOURS], NeighbourNames.NUMBER_ONLY),
            panelFolded = it[PANEL_FOLDED] ?: false,
        )
    }

    suspend fun save(settings: CaptionSettings) {
        dataStore.edit {
            it[PLACE] = settings.place.name
            it[LOOK] = settings.look.name
            val fields = settings.fields
            if (fields == null) it.remove(FIELDS) else it[FIELDS] = encodeCaptionFields(fields)
            it[NAME_MODE] = settings.nameMode.name
            it[NEIGHBOURS] = settings.neighbours.name
            it[PANEL_FOLDED] = settings.panelFolded
        }
    }

    private companion object {
        val PLACE = stringPreferencesKey("caption_place")
        val LOOK = stringPreferencesKey("caption_look")
        val FIELDS = stringPreferencesKey("caption_fields")
        val NAME_MODE = stringPreferencesKey("caption_name_mode")
        val NEIGHBOURS = stringPreferencesKey("caption_neighbours")
        val PANEL_FOLDED = booleanPreferencesKey("caption_panel_folded")
    }
}

/** The fields as a JSON array of `field:<key>` and `custom:<column>`. */
internal fun encodeCaptionFields(fields: List<CaptionField>): String = ApiJson.encodeToString(
    ListSerializer(String.serializer()),
    fields.map {
        when (it) {
            is CaptionField.Field -> FIELD_PREFIX + it.key
            is CaptionField.Custom -> CUSTOM_PREFIX + it.column
        }
    },
)

/** The fields stored by [encodeCaptionFields]; entries it cannot read are skipped, and null means unreadable. */
internal fun decodeCaptionFields(json: String): List<CaptionField>? {
    val entries = try {
        ApiJson.decodeFromString(ListSerializer(String.serializer()), json)
    } catch (_: SerializationException) {
        return null
    }
    return entries.mapNotNull {
        when {
            it.startsWith(FIELD_PREFIX) -> CaptionField.Field(it.removePrefix(FIELD_PREFIX))
            it.startsWith(CUSTOM_PREFIX) -> CaptionField.Custom(it.removePrefix(CUSTOM_PREFIX))
            else -> null
        }
    }
}

/** The constant named [name], or [default] when there is none (not saved yet, or from another version). */
private inline fun <reified T : Enum<T>> enumOr(name: String?, default: T): T =
    enumValues<T>().firstOrNull { it.name == name } ?: default

private const val FIELD_PREFIX = "field:"
private const val CUSTOM_PREFIX = "custom:"
