package io.github.squarepot.app.recognition

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TagCodeTest {
    @Test
    fun `accepts six digits including leading zeros`() {
        assertEquals("000042", TagCode.parse("000042")?.value)
        assertEquals("123456", TagCode.parse("123456")?.value)
    }

    @Test
    fun `rejects the reserved number and anything that is not exactly six digits`() {
        listOf(null, "", "000000", "12345", "1234567", "12345a", " 12345", "١٢٣٤٥٦", "https://x/123456").forEach {
            assertNull("'$it' must be rejected", TagCode.parse(it))
        }
    }
}
