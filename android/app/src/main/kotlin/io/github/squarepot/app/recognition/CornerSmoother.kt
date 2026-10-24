// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.recognition

/**
 * Steadies the drawn labels: each label's four corners go through a [OneEuroFilter] per
 * coordinate, keyed by its number. A label the decoder did not see this frame (shown only by
 * [DetectionHold]) keeps its last smoothed corners; a label no longer shown is forgotten, so when
 * it comes back it starts where it is instead of sliding in from where it was.
 *
 * Only for drawing: selection works on the raw detections. Not thread-safe.
 */
class CornerSmoother(params: Params = Params()) {

    /** [minCutoff] in Hz; [beta] per frame pixel per second. See [OneEuroFilter]. */
    data class Params(val minCutoff: Float = 1f, val beta: Float = 0.05f) {
        init {
            require(minCutoff > 0f) { "minCutoff must be positive" }
            require(beta >= 0f) { "beta must not be negative" }
        }
    }

    /** Changing the parameters restarts every label's filters. */
    var params: Params = params
        set(value) {
            field = value
            tracks.clear()
        }

    private class Track(params: Params) {
        val filters = List(CORNERS * 2) { OneEuroFilter(params.minCutoff, params.beta) }
        var smoothed: Detection? = null
    }

    private val tracks = HashMap<TagCode, Track>()

    /** [shown] is what [DetectionHold] returned; [seen] the labels decoded in this frame. */
    fun update(shown: List<Detection>, seen: List<Detection>, timestampMillis: Long): List<Detection> {
        val seenCodes = seen.mapTo(HashSet()) { it.code }
        tracks.keys.retainAll(shown.mapTo(HashSet()) { it.code })
        return shown.map { detection ->
            val track = tracks.getOrPut(detection.code) { Track(params) }
            val previous = track.smoothed
            if (detection.code !in seenCodes && previous != null) return@map previous
            val corners = detection.corners.mapIndexed { i, p ->
                Point(
                    track.filters[2 * i].filter(p.x, timestampMillis),
                    track.filters[2 * i + 1].filter(p.y, timestampMillis),
                )
            }
            Detection(detection.code, corners).also { track.smoothed = it }
        }
    }

    fun clear() = tracks.clear()

    private companion object {
        const val CORNERS = 4
    }
}
