// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.recognition

/**
 * Keeps each label on screen for [holdMillis] after the decoder last saw it, at the position it was
 * last seen, so frames and numbers do not blink when the decoder misses a label for a frame or two.
 *
 * Not thread-safe: feed it from one analysis thread.
 */
class DetectionHold(private val holdMillis: Long = 300) {
    init {
        require(holdMillis >= 0) { "holdMillis must not be negative" }
    }

    private val lastSeen = LinkedHashMap<TagCode, Pair<Detection, Long>>()

    /** Takes one frame's detections and returns the labels to show: these and the recently missed ones. */
    fun update(detections: List<Detection>, timestampMillis: Long): List<Detection> {
        detections.forEach { lastSeen[it.code] = it to timestampMillis }
        lastSeen.values.removeAll { (_, seenAt) -> timestampMillis - seenAt > holdMillis }
        return lastSeen.values.map { it.first }
    }

    fun clear() = lastSeen.clear()
}
