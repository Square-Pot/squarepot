// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.recognition

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs

class OneEuroFilterTest {
    private val frameMillis = 33L

    @Test
    fun `the first value passes through`() {
        assertEquals(42f, OneEuroFilter(1f, 0.05f).filter(42f, 0), 0f)
    }

    @Test
    fun `jitter around a still value is damped`() {
        val filter = OneEuroFilter(minCutoff = 1f, beta = 0.05f)
        // A label at x = 100 whose corner wobbles by ±3 px from frame to frame.
        val out = (0 until 60).map { i -> filter.filter(if (i % 2 == 0) 103f else 97f, i * frameMillis) }
        val wobble = out.drop(30).zipWithNext { a, b -> abs(a - b) }.max()
        assertTrue("wobble $wobble px", wobble < 1.5f)
    }

    @Test
    fun `a fast move is followed closely`() {
        val filter = OneEuroFilter(minCutoff = 1f, beta = 0.05f)
        // Panning at 600 px/s: 20 px per frame.
        var last = 0f
        for (i in 0 until 30) last = filter.filter(i * 20f, i * frameMillis)
        val lag = 29 * 20f - last
        assertTrue("lag $lag px", lag < 30f)
    }

    @Test
    fun `without beta a fast move lags far behind`() {
        val plain = OneEuroFilter(minCutoff = 1f, beta = 0f)
        var last = 0f
        for (i in 0 until 30) last = plain.filter(i * 20f, i * frameMillis)
        assertTrue(29 * 20f - last > 60f)
    }

    @Test
    fun `a repeated or older timestamp changes nothing`() {
        val filter = OneEuroFilter(1f, 0.05f)
        filter.filter(10f, 100)
        assertEquals(10f, filter.filter(50f, 100), 0f)
        assertEquals(10f, filter.filter(50f, 90), 0f)
    }
}
