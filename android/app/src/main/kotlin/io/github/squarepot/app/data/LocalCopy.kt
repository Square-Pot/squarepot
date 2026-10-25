// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import io.github.squarepot.app.data.api.ApiJson
import io.github.squarepot.app.data.api.FieldSchemaDto
import io.github.squarepot.app.data.local.CollectionColumns
import io.github.squarepot.app.data.local.CopyDao
import io.github.squarepot.app.data.local.PlantEntity
import kotlinx.coroutines.flow.Flow

/** One field of a plant, ready to show: the schema's label in the UI language and the value. */
data class FieldValue(val key: String, val label: String, val value: String)

/** A piece of text, set in italics or not. */
data class TextRun(val text: String, val italic: Boolean = false)

data class PlantView(
    val id: String,
    val tag: String?,
    val collectionName: String,
    val fields: List<FieldValue>,
    /** The botanical name (see [botanicalName]); empty when the copy has no schema yet. */
    val name: List<TextRun> = emptyList(),
    /** Values of the collection's custom columns by name. */
    val custom: Map<String, String> = emptyMap(),
)

/** Reads the local copy. Never touches the network: this is what the camera path uses. */
class LocalCopy(private val dao: CopyDao) {
    /** Every plant with the label number [input] ("4217" or "004217"); empty when the number is invalid. */
    suspend fun plantsByTag(input: String, language: String): List<PlantView> {
        val plants = normaliseTag(input)?.let { dao.plantsByTag(it) }.orEmpty()
        if (plants.isEmpty()) return emptyList()
        val schema = schema()
        val collections = dao.collectionNames().associate { it.id to it.name }
        return plants.map { it.toView(collections[it.collectionId] ?: it.collectionId, schema, language) }
    }

    /** The plant whose botanical name is longest, the hardest case for a caption; null when the copy is empty. */
    suspend fun longestNamed(language: String): PlantView? {
        val schema = schema()
        val longest = dao.allPlants().maxByOrNull { botanicalName(schema, it.fields).plain().length } ?: return null
        val collections = dao.collectionNames().associate { it.id to it.name }
        return longest.toView(collections[longest.collectionId] ?: longest.collectionId, schema, language)
    }

    /** Each collection's custom columns, for choosing which of them a caption shows. */
    fun customColumns(): Flow<List<CollectionColumns>> = dao.observeCustomColumns()

    /** The copy's field schema; null before the first sync. */
    suspend fun schema(): FieldSchemaDto? = dao.state()?.schemaJson?.let {
        ApiJson.decodeFromString(FieldSchemaDto.serializer(), it)
    }
}

/** A label number with leading zeros ("004217"), or null when [input] is not one; "000000" is reserved. */
fun normaliseTag(input: String): String? {
    val digits = input.trim()
    if (digits.isEmpty() || digits.length > TAG_LENGTH || !digits.all { it in '0'..'9' }) return null
    return digits.padStart(TAG_LENGTH, '0').takeIf { it != RESERVED_TAG }
}

/** The plant's fields in the schema's order with its labels; keys the schema does not know come last, as is. */
fun PlantEntity.toView(collectionName: String, schema: FieldSchemaDto?, language: String): PlantView {
    val known = schema?.fields.orEmpty()
        .filter { it.key in fields }
        .map { FieldValue(it.key, it.label.forLanguage(language), fields.getValue(it.key)) }
    val knownKeys = known.mapTo(HashSet()) { it.key }
    val unknown = fields.filterKeys { it !in knownKeys }.map { (key, value) -> FieldValue(key, key, value) }
    return PlantView(id, tag, collectionName, known + unknown, botanicalName(schema, fields), custom)
}

private const val TAG_LENGTH = 6
private const val RESERVED_TAG = "000000"
