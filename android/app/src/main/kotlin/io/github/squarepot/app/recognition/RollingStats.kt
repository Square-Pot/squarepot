// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.recognition

import kotlin.math.ceil

/** Decode rate and latency over the last [capacity] frames of one decoder. Not thread-safe. */
class RollingStats(private val capacity: Int = 120) {

    data class Snapshot(val frames: Int, val hitRate: Float, val medianMillis: Float, val p95Millis: Float) {
        companion object {
            val EMPTY = Snapshot(0, 0f, 0f, 0f)
        }
    }

    private val millis = ArrayDeque<Float>(capacity)
    private val hits = ArrayDeque<Boolean>(capacity)

    init {
        require(capacity > 0) { "capacity must be positive" }
    }

    /** Records one frame: how long the decoder took and whether it found at least one label. */
    fun add(decodeMillis: Float, hit: Boolean) {
        if (millis.size == capacity) {
            millis.removeFirst()
            hits.removeFirst()
        }
        millis.addLast(decodeMillis)
        hits.addLast(hit)
    }

    fun clear() {
        millis.clear()
        hits.clear()
    }

    fun snapshot(): Snapshot {
        if (millis.isEmpty()) return Snapshot.EMPTY
        val sorted = millis.sorted()
        return Snapshot(
            frames = sorted.size,
            hitRate = hits.count { it }.toFloat() / hits.size,
            medianMillis = percentile(sorted, MEDIAN),
            p95Millis = percentile(sorted, P95),
        )
    }

    private companion object {
        const val MEDIAN = 0.5
        const val P95 = 0.95

        /** Nearest-rank percentile of an ascending list. */
        fun percentile(sorted: List<Float>, p: Double): Float {
            val rank = ceil(p * sorted.size).toInt().coerceIn(1, sorted.size)
            return sorted[rank - 1]
        }
    }
}
