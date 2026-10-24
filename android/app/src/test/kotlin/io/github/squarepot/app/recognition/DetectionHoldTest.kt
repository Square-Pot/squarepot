// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.recognition

import org.junit.Assert.assertEquals
import org.junit.Test

class DetectionHoldTest {
    private fun tag(code: String, x: Float = 100f): Detection = Detection(
        requireNotNull(TagCode.parse(code)),
        listOf(Point(x, 100f), Point(x + 50f, 100f), Point(x + 50f, 150f), Point(x, 150f)),
    )

    private fun List<Detection>.codes() = map { it.code.value }

    @Test
    fun `a label missed for one frame stays on screen`() {
        val hold = DetectionHold(holdMillis = 300)
        hold.update(listOf(tag("111111"), tag("222222", x = 300f)), 0)
        assertEquals(listOf("111111", "222222"), hold.update(listOf(tag("111111")), 33).codes())
    }

    @Test
    fun `a label is dropped once missed for longer than the hold`() {
        val hold = DetectionHold(holdMillis = 300)
        hold.update(listOf(tag("111111")), 0)
        assertEquals(listOf("111111"), hold.update(emptyList(), 300).codes())
        assertEquals(emptyList<String>(), hold.update(emptyList(), 301).codes())
    }

    @Test
    fun `a held label keeps its last position and moves with the next sighting`() {
        val hold = DetectionHold()
        hold.update(listOf(tag("111111", x = 100f)), 0)
        assertEquals(tag("111111", x = 100f), hold.update(emptyList(), 33).single())
        assertEquals(tag("111111", x = 140f), hold.update(listOf(tag("111111", x = 140f)), 66).single())
    }

    @Test
    fun `clear forgets every label`() {
        val hold = DetectionHold()
        hold.update(listOf(tag("111111")), 0)
        hold.clear()
        assertEquals(emptyList<String>(), hold.update(emptyList(), 10).codes())
    }
}
