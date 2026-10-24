// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class CaptionSettingsTest {
    private val fields = listOf(
        CaptionField.Custom("Marathon"),
        CaptionField.Field("name"),
        CaptionField.Custom("field:odd column"),
    )

    @Test
    fun `the field list survives storage in order`() {
        assertEquals(fields, decodeCaptionFields(encodeCaptionFields(fields)))
        assertEquals(emptyList<CaptionField>(), decodeCaptionFields(encodeCaptionFields(emptyList())))
    }

    @Test
    fun `entries from another version are skipped, garbage is unreadable`() {
        assertEquals(listOf(CaptionField.Field("ex")), decodeCaptionFields("""["field:ex", "preset:chat"]"""))
        assertNull(decodeCaptionFields("not json"))
    }

    @Test
    fun `until the owner chooses, captions follow the default for the current columns`() {
        val settings = CaptionSettings()
        assertEquals(defaultCaptionFields(listOf("Shelf")), settings.fieldsFor(listOf("Shelf")))
        assertEquals(fields, settings.copy(fields = fields).fieldsFor(listOf("Shelf")))
    }
}
