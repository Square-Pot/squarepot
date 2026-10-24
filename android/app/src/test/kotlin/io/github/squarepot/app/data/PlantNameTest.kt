// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import io.github.squarepot.app.data.api.ComputedFieldDto
import io.github.squarepot.app.data.api.DisplayDto
import io.github.squarepot.app.data.api.FieldDefinitionDto
import io.github.squarepot.app.data.api.FieldSchemaDto
import io.github.squarepot.app.data.api.LabelDto
import org.junit.Assert.assertEquals
import org.junit.Test

class PlantNameTest {
    private fun field(key: String, display: DisplayDto?) =
        FieldDefinitionDto(key, "text", LabelDto(key, key), "taxonomy", display = display)

    // The display rules of schema/fields.yaml.
    private val schema = FieldSchemaDto(
        version = 1,
        fields = listOf(
            field("genus", DisplayDto(italic = true, case = "title")),
            field("affinity", DisplayDto(prefix = "aff.", italic = true)),
            field("species", DisplayDto(italic = true, case = "lower")),
            field("subspecies", DisplayDto(prefix = "subsp.", italic = true, case = "lower")),
            field("variety", DisplayDto(prefix = "var.", italic = true, case = "lower")),
            field("cultivar", DisplayDto(quote = true)),
            field("notes", null),
        ),
        computed = listOf(
            ComputedFieldDto(
                "name",
                LabelDto("Name", "Название"),
                listOf("genus", "affinity", "species", "subspecies", "variety", "form", "cultivar"),
            ),
        ),
    )

    @Test
    fun `the name joins the taxonomy fields with their prefixes, case and quotes`() {
        val fields = mapOf(
            "genus" to "LITHOPS",
            "species" to "Gracilidelineata",
            "subspecies" to "gracilidelineata",
            "variety" to "waldroniae",
            "notes" to "not part of the name",
        )
        assertEquals(
            listOf(
                TextRun("Lithops", italic = true),
                TextRun(" "),
                TextRun("gracilidelineata", italic = true),
                TextRun(" "),
                TextRun("subsp. "),
                TextRun("gracilidelineata", italic = true),
                TextRun(" "),
                TextRun("var. "),
                TextRun("waldroniae", italic = true),
            ),
            botanicalName(schema, fields),
        )
    }

    @Test
    fun `empty fields are skipped and a cultivar is quoted upright`() {
        val fields = mapOf("genus" to "Lithops", "species" to " ", "affinity" to "lesliei", "cultivar" to "Albinica")
        assertEquals("Lithops aff. lesliei ‘Albinica’", botanicalName(schema, fields).plain())
        assertEquals(TextRun("‘Albinica’", italic = false), botanicalName(schema, fields).last())
    }

    @Test
    fun `no schema or no taxonomy gives no name`() {
        assertEquals(emptyList<TextRun>(), botanicalName(null, mapOf("genus" to "Lithops")))
        assertEquals(emptyList<TextRun>(), botanicalName(schema, mapOf("notes" to "x")))
    }
}
