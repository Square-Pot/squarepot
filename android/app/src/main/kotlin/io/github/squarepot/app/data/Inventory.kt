// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.MutablePreferences
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import io.github.squarepot.app.data.api.FieldSchemaDto
import io.github.squarepot.app.data.local.PlantEntity
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

/**
 * An inventory walk (ADR 0008, variant A): which plants it covers and since when a sighting counts.
 * The scope is a collection, optionally narrowed to the plants with one [value] in one [column],
 * such as a shelf; former plants (with a status) and plants without a number are left out.
 */
data class InventoryWalk(
    /** Inventory mode is on: a tap on a label opens the plant's card. */
    val active: Boolean = false,
    /** The collection walked; null for all of them. */
    val collectionId: String? = null,
    /** A field key or custom column that narrows the walk, with the [value] it must have. */
    val column: String? = null,
    val value: String? = null,
    /** When the walk began, epoch millis: sightings before it do not count. */
    val startedAt: Long = 0,
) {
    fun covers(plant: PlantEntity): Boolean = plant.tag != null &&
        plant.fields[STATUS].isNullOrEmpty() &&
        (collectionId == null || plant.collectionId == collectionId) &&
        (column == null || plant.valueOf(column) == value)

    /** Whether [plant] was seen in this walk, by any phone ([PlantEntity.lastSeen]) or this one ([seenHere]). */
    fun saw(plant: PlantEntity, seenHere: Set<String>): Boolean =
        plant.tag in seenHere || (plant.lastSeen ?: Long.MIN_VALUE) >= startedAt

    fun progress(plants: List<PlantEntity>, seenHere: Set<String>): WalkProgress {
        val covered = plants.filter(::covers)
        return WalkProgress(seen = covered.count { saw(it, seenHere) }, total = covered.size)
    }

    /** Numbers seen in this walk, in scope or not, for the camera's ✓. */
    fun seenTags(plants: List<PlantEntity>, seenHere: Set<String>): Set<String> =
        seenHere + plants.filter { (it.lastSeen ?: Long.MIN_VALUE) >= startedAt }.mapNotNull { it.tag }
}

data class WalkProgress(val seen: Int, val total: Int)

/** The columns a walk can be narrowed by: the genus, then the collection's own [customColumns]. */
fun walkColumns(customColumns: List<String>): List<String> = listOf(GENUS) + customColumns

/** The values [column] has among the current plants of [collectionId], most frequent first. */
fun columnValues(plants: List<PlantEntity>, collectionId: String?, column: String): List<String> = plants
    .filter { (collectionId == null || it.collectionId == collectionId) && it.fields[STATUS].isNullOrEmpty() }
    .mapNotNull { it.valueOf(column)?.takeIf(String::isNotBlank) }
    .groupingBy { it }
    .eachCount()
    .entries
    .sortedWith(compareByDescending<Map.Entry<String, Int>> { it.value }.thenBy { it.key })
    .map { it.key }

/** The label in [language] of [key], a value of [field] (such as status `lost`), or [key] when the schema has none. */
fun FieldSchemaDto?.valueLabel(field: String, key: String, language: String): String =
    this?.fields?.firstOrNull { it.key == field }?.values?.firstOrNull { it.key == key }?.label?.forLanguage(language)
        ?: key

private fun PlantEntity.valueOf(column: String): String? = fields[column] ?: custom[column]

/** The walk, kept on the phone so it survives restarts in the middle of a greenhouse. */
class InventoryStore(private val dataStore: DataStore<Preferences>) {
    val walk: Flow<InventoryWalk> = dataStore.data.map { it.toWalk() }

    /** Changes the stored walk in one step, so two quick changes cannot undo each other. */
    suspend fun update(change: (InventoryWalk) -> InventoryWalk) {
        dataStore.edit { it.write(change(it.toWalk())) }
    }

    private fun Preferences.toWalk() = InventoryWalk(
        active = this[ACTIVE] ?: false,
        collectionId = this[COLLECTION],
        column = this[COLUMN],
        value = this[VALUE],
        startedAt = this[STARTED_AT] ?: 0,
    )

    private fun MutablePreferences.write(walk: InventoryWalk) {
        this[ACTIVE] = walk.active
        put(COLLECTION, walk.collectionId)
        put(COLUMN, walk.column)
        put(VALUE, walk.value)
        this[STARTED_AT] = walk.startedAt
    }

    private fun MutablePreferences.put(key: Preferences.Key<String>, value: String?) {
        if (value == null) remove(key) else this[key] = value
    }

    private companion object {
        val ACTIVE = booleanPreferencesKey("inventory_active")
        val COLLECTION = stringPreferencesKey("inventory_collection")
        val COLUMN = stringPreferencesKey("inventory_column")
        val VALUE = stringPreferencesKey("inventory_value")
        val STARTED_AT = longPreferencesKey("inventory_started_at")
    }
}

private const val STATUS = "status"
private const val GENUS = "genus"
