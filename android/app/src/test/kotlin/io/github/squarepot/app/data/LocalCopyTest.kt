// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import io.github.squarepot.app.data.api.FieldDefinitionDto
import io.github.squarepot.app.data.api.FieldSchemaDto
import io.github.squarepot.app.data.api.LabelDto
import io.github.squarepot.app.data.local.PlantEntity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LocalCopyTest {
    @Test
    fun `label numbers get their leading zeros`() {
        assertEquals("004217", normaliseTag("4217"))
        assertEquals("004217", normaliseTag(" 004217 "))
        assertEquals("000001", normaliseTag("1"))
    }

    @Test
    fun `invalid and reserved numbers are rejected`() {
        assertNull(normaliseTag(""))
        assertNull(normaliseTag("1234567"))
        assertNull(normaliseTag("12a4"))
        assertNull(normaliseTag("-1"))
        assertNull(normaliseTag("0"))
        assertNull(normaliseTag("000000"))
    }

    private val schema = FieldSchemaDto(
        version = 1,
        fields = listOf(
            FieldDefinitionDto("genus", "text", LabelDto("Genus", "Род"), "basic"),
            FieldDefinitionDto("species", "text", LabelDto("Species", "Вид"), "basic"),
        ),
    )

    private val plant = PlantEntity(
        id = "p1",
        collectionId = "main",
        tag = "004217",
        sheetRow = 2,
        fields = mapOf("species" to "lesliei", "added_later" to "x", "genus" to "Lithops"),
        custom = mapOf("Marathon" to "yes"),
    )

    @Test
    fun `fields follow the schema order and labels, unknown keys last`() {
        val view = plant.toView("Main", schema, "en")
        assertEquals(
            listOf(
                FieldValue("genus", "Genus", "Lithops"),
                FieldValue("species", "Species", "lesliei"),
                FieldValue("added_later", "added_later", "x"),
            ),
            view.fields,
        )
    }

    @Test
    fun `custom column values are carried as they are`() {
        assertEquals(mapOf("Marathon" to "yes"), plant.toView("Main", schema, "en").custom)
    }

    @Test
    fun `labels follow the UI language, English otherwise`() {
        assertEquals("Род", plant.toView("Main", schema, "ru").fields.first().label)
        assertEquals("Genus", plant.toView("Main", schema, "de").fields.first().label)
    }

    @Test
    fun `without a schema the raw keys are shown`() {
        val labels = plant.toView("Main", null, "en").fields.map { it.label }
        assertEquals(listOf("species", "added_later", "genus"), labels)
    }
}
