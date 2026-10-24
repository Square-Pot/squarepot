// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.recognition

import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

class CornerSmootherTest {
    private fun tag(code: String, x: Float): Detection = Detection(
        requireNotNull(TagCode.parse(code)),
        listOf(Point(x, 100f), Point(x + 50f, 100f), Point(x + 50f, 150f), Point(x, 150f)),
    )

    @Test
    fun `a new label is drawn where it is`() {
        val smoother = CornerSmoother()
        val a = tag("111111", 100f)
        assertEquals(listOf(a), smoother.update(listOf(a), listOf(a), 0))
    }

    @Test
    fun `a jump of a seen label is smoothed`() {
        val smoother = CornerSmoother(CornerSmoother.Params(minCutoff = 1f, beta = 0f))
        smoother.update(listOf(tag("111111", 100f)), listOf(tag("111111", 100f)), 0)
        val moved = tag("111111", 110f)
        val x = smoother.update(listOf(moved), listOf(moved), 33).single().corners[0].x
        assertTrue("x = $x", x > 100f && x < 110f)
    }

    @Test
    fun `a held label keeps its last smoothed corners`() {
        val smoother = CornerSmoother()
        val a = tag("111111", 100f)
        val first = smoother.update(listOf(a), listOf(a), 0).single()
        assertSame(first, smoother.update(listOf(a), emptyList(), 33).single())
    }

    @Test
    fun `a label that was dropped starts afresh when it comes back`() {
        val smoother = CornerSmoother(CornerSmoother.Params(minCutoff = 1f, beta = 0f))
        smoother.update(listOf(tag("111111", 100f)), listOf(tag("111111", 100f)), 0)
        smoother.update(emptyList(), emptyList(), 400)
        val back = tag("111111", 300f)
        assertEquals(back, smoother.update(listOf(back), listOf(back), 433).single())
    }

    @Test
    fun `new parameters restart the filters`() {
        val smoother = CornerSmoother(CornerSmoother.Params(minCutoff = 1f, beta = 0f))
        smoother.update(listOf(tag("111111", 100f)), listOf(tag("111111", 100f)), 0)
        smoother.params = CornerSmoother.Params(minCutoff = 2f, beta = 0f)
        // Restarted filters let the first value through: no smoothing towards the old position.
        val moved = tag("111111", 110f)
        assertEquals(moved, smoother.update(listOf(moved), listOf(moved), 33).single())
    }
}
