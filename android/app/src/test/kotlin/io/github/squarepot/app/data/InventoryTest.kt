// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import io.github.squarepot.app.data.api.FieldDefinitionDto
import io.github.squarepot.app.data.api.FieldSchemaDto
import io.github.squarepot.app.data.api.FieldValueDto
import io.github.squarepot.app.data.api.LabelDto
import io.github.squarepot.app.data.local.PlantEntity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Which plants a walk covers, what counts as seen in it, and what narrows it. */
class InventoryTest {
    @Suppress("LongParameterList") // One per thing a walk looks at.
    private fun plant(
        tag: String?,
        collection: String = "main",
        genus: String = "Lithops",
        shelf: String? = null,
        status: String? = null,
        lastSeen: Long? = null,
    ) = PlantEntity(
        id = "p$tag",
        collectionId = collection,
        tag = tag,
        sheetRow = 2,
        fields = mapOfNotNull("genus" to genus, "status" to status),
        custom = mapOfNotNull("Полка" to shelf),
        lastSeen = lastSeen,
    )

    private fun mapOfNotNull(vararg pairs: Pair<String, String?>): Map<String, String> =
        pairs.mapNotNull { (k, v) -> v?.let { k to it } }.toMap()

    @Test
    fun `a walk covers numbered current plants of its collection and column value`() {
        val walk = InventoryWalk(collectionId = "main", column = "Полка", value = "B-3")
        assertTrue(walk.covers(plant("000001", shelf = "B-3")))
        assertFalse("another shelf", walk.covers(plant("000002", shelf = "B-4")))
        assertFalse("another collection", walk.covers(plant("000003", collection = "other", shelf = "B-3")))
        assertFalse("no number", walk.covers(plant(null, shelf = "B-3")))
        assertFalse("a former plant", walk.covers(plant("000004", shelf = "B-3", status = "dead")))
    }

    @Test
    fun `without a collection or column a walk covers every current numbered plant`() {
        val walk = InventoryWalk()
        assertTrue(walk.covers(plant("000001", collection = "a")))
        assertTrue(walk.covers(plant("000002", collection = "b", genus = "Conophytum")))
    }

    @Test
    fun `a plant counts as seen from the walk's start, by any phone or this one`() {
        val walk = InventoryWalk(startedAt = 1_000L)
        val plants = listOf(
            plant("000001", lastSeen = 1_500L),
            plant("000002", lastSeen = 500L),
            plant("000003"),
            plant("000004", status = "lost", lastSeen = 2_000L),
        )
        val progress = walk.progress(plants, seenHere = setOf("000003"))
        assertEquals(WalkProgress(seen = 2, total = 3), progress)
        assertEquals(setOf("000001", "000003", "000004"), walk.seenTags(plants, setOf("000003")))
    }

    @Test
    fun `a column's values come most frequent first, former plants left out`() {
        val plants = listOf(
            plant("000001", shelf = "B-3"),
            plant("000002", shelf = "A-1"),
            plant("000003", shelf = "B-3"),
            plant("000004", shelf = "C-9", status = "sold"),
            plant("000005", shelf = " "),
            plant("000006", collection = "other", shelf = "Z"),
        )
        assertEquals(listOf("B-3", "A-1"), columnValues(plants, "main", "Полка"))
        assertEquals(listOf("Lithops"), columnValues(plants, "main", "genus"))
        assertEquals(listOf("B-3", "A-1", "Z"), columnValues(plants, null, "Полка"))
    }

    @Test
    fun `a walk is narrowed by the genus or the collection's own columns`() {
        assertEquals(listOf("genus", "Полка", "Ряд"), walkColumns(listOf("Полка", "Ряд")))
    }

    @Test
    fun `a status is shown by its label, or its key when the schema has none`() {
        val status = FieldDefinitionDto(
            key = "status",
            type = "text",
            label = LabelDto("Status", "Статус"),
            group = "extra",
            values = listOf(FieldValueDto("lost", LabelDto("Lost", "Потерян"))),
        )
        val schema = FieldSchemaDto(version = 1, fields = listOf(status))
        assertEquals("Потерян", schema.valueLabel("status", "lost", "ru"))
        assertEquals("Lost", schema.valueLabel("status", "lost", "en"))
        assertEquals("gifted", schema.valueLabel("status", "gifted", "ru"))
        assertEquals("lost", null.valueLabel("status", "lost", "ru"))
    }
}
