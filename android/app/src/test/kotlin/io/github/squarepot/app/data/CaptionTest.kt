// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import io.github.squarepot.app.data.api.ComputedFieldDto
import io.github.squarepot.app.data.api.DisplayDto
import io.github.squarepot.app.data.api.FieldDefinitionDto
import io.github.squarepot.app.data.api.FieldSchemaDto
import io.github.squarepot.app.data.api.LabelDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class CaptionTest {
    private fun field(key: String, display: DisplayDto? = null) =
        FieldDefinitionDto(key, "text", LabelDto(key, key), "basic", display = display)

    // The display rules of schema/fields.yaml that these captions use.
    private val schema = FieldSchemaDto(
        version = 1,
        fields = listOf(
            field("field_number", DisplayDto(case = "upper")),
            field("genus", DisplayDto(italic = true, case = "title")),
            field("species", DisplayDto(italic = true, case = "lower")),
            field("variety", DisplayDto(prefix = "var.", italic = true, case = "lower")),
            field("ex", DisplayDto(prefix = "ex")),
            field("locality"),
            field("seeding_date"),
            field("purchase_date"),
        ),
        computed = listOf(
            ComputedFieldDto("name", LabelDto("Name", "Название"), listOf("genus", "species", "variety")),
        ),
    )

    private val today = LocalDate.of(2026, 10, 25)

    private fun plant(fields: Map<String, String>, custom: Map<String, String> = emptyMap()) = PlantView(
        id = "p1",
        tag = "004217",
        collectionName = "Main",
        fields = fields.map { (key, value) -> FieldValue(key, key, value) },
        name = botanicalName(schema, fields),
        custom = custom,
    )

    private val theresae = plant(
        mapOf(
            "field_number" to "pv 2187a",
            "genus" to "Mammillaria",
            "species" to "theresae",
            "variety" to "albiflora",
            "ex" to "Collector",
            "seeding_date" to "2022-03-05",
        ),
        custom = mapOf("Marathon" to "Contest 2023", "Shelf" to " "),
    )

    private fun caption(chosen: List<CaptionField>, mode: NameMode = NameMode.FULL, plant: PlantView = theresae) =
        caption(plant, schema, chosen, mode, today)

    private val name = CaptionField.Field("name")

    @Test
    fun `the default is field number, name, ex and the first custom column`() {
        assertEquals(
            listOf(
                CaptionField.Field("field_number"),
                name,
                CaptionField.Field("ex"),
                CaptionField.Custom("Marathon"),
            ),
            defaultCaptionFields(listOf("Marathon", "Shelf")),
        )
        assertEquals(3, defaultCaptionFields(emptyList()).size)
    }

    @Test
    fun `lines follow the chosen order with each field's display rules`() {
        val lines = caption(
            listOf(CaptionField.Custom("Marathon"), CaptionField.Field("ex"), name, CaptionField.Field("field_number")),
        )
        assertEquals(
            listOf(
                CaptionLine.Custom("Marathon", "Contest 2023"),
                CaptionLine.Text(listOf(TextRun("ex "), TextRun("Collector"))),
                CaptionLine.Name(theresae.name, maxLines = null),
                CaptionLine.FieldNumber("PV 2187A"),
            ),
            lines,
        )
    }

    @Test
    fun `fields and custom columns the plant has no value for are left out`() {
        val lines = caption(
            listOf(CaptionField.Field("locality"), CaptionField.Custom("Shelf"), CaptionField.Custom("Soil"), name),
        )
        assertEquals(listOf(CaptionLine.Name(theresae.name, maxLines = null)), lines)
    }

    @Test
    fun `two lines limits the name, short genus keeps its initial`() {
        assertEquals(2, (caption(listOf(name), NameMode.TWO_LINES).single() as CaptionLine.Name).maxLines)
        val short = caption(listOf(name), NameMode.SHORT_GENUS).single() as CaptionLine.Name
        assertEquals("M. theresae var. albiflora", short.runs.plain())
        assertTrue(short.runs.first().italic)
    }

    @Test
    fun `a neighbour's short name is the genus initial and the species`() {
        assertEquals(
            listOf(TextRun("M.", italic = true), TextRun(" "), TextRun("theresae", italic = true)),
            shortName(theresae, schema),
        )
        assertTrue(shortName(plant(mapOf("ex" to "Collector")), schema).isEmpty())
    }

    @Test
    fun `age counts whole months from seeding, else from purchase`() {
        assertEquals(55, ageInMonths(mapOf("seeding_date" to "2022-03-05"), today))
        assertEquals(1, ageInMonths(mapOf("purchase_date" to "2026-09-25"), today))
        assertEquals(0, ageInMonths(mapOf("seeding_date" to "2026-10-01", "purchase_date" to "2020-01-01"), today))
        assertNull(ageInMonths(mapOf("seeding_date" to "spring"), today))
        assertNull(ageInMonths(mapOf("seeding_date" to "2027-01-01"), today))
        assertEquals(
            listOf(CaptionLine.Age(55)),
            caption(listOf(CaptionField.Field("age"))),
        )
    }

    @Test
    fun `the copy text joins the lines with a middle dot`() {
        val chosen = listOf(
            CaptionField.Field("field_number"),
            name,
            CaptionField.Field("age"),
            CaptionField.Custom("Marathon"),
        )
        val lines = caption(chosen)
        assertEquals(
            "PV 2187A · Mammillaria theresae var. albiflora · 4 yr · Marathon: Contest 2023",
            lines.copyText { "${it / 12} yr" },
        )
    }
}
