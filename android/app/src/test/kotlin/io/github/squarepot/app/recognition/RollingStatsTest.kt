package io.github.squarepot.app.recognition

import org.junit.Assert.assertEquals
import org.junit.Test

class RollingStatsTest {
    @Test
    fun `empty stats are zero`() {
        assertEquals(RollingStats.Snapshot.EMPTY, RollingStats().snapshot())
    }

    @Test
    fun `computes hit rate and nearest-rank percentiles`() {
        val stats = RollingStats(capacity = 100)
        (1..20).forEach { stats.add(decodeMillis = it.toFloat(), hit = it % 4 != 0) }
        val s = stats.snapshot()
        assertEquals(20, s.frames)
        assertEquals(0.75f, s.hitRate, 1e-6f)
        assertEquals(10f, s.medianMillis)
        assertEquals(19f, s.p95Millis)
    }

    @Test
    fun `keeps only the last frames`() {
        val stats = RollingStats(capacity = 3)
        stats.add(100f, hit = false)
        listOf(1f, 2f, 3f).forEach { stats.add(it, hit = true) }
        val s = stats.snapshot()
        assertEquals(3, s.frames)
        assertEquals(1f, s.hitRate, 1e-6f)
        assertEquals(3f, s.p95Millis)
    }
}
