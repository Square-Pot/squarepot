// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.recognition

import kotlin.math.abs

/**
 * Picks the one label to show, frame by frame, for the single-plant mode: the largest, which is
 * the nearest pot's.
 *
 * - Each detection is scored by its share of the frame area, weighted down by up to
 *   [SIDE_PENALTY] as it moves from the vertical middle of the frame to the left or right edge.
 *   Size decides; horizontal position only separates labels of similar size. There is no
 *   penalty for vertical position: the plant fills the middle of the frame and its label sits on
 *   the rim above or below it.
 * - Hysteresis: once a target is chosen, a different label replaces it only when it scores
 *   [Config.switchMargin] times higher, so the target does not flicker between neighbours.
 * - A target is locked after [Config.framesToLock] frames in which it was seen and chosen.
 *   Frames where the decoder misses it for no longer than [Config.holdMillis] neither count nor
 *   reset the count; a longer gap, or another label taking over, starts over.
 * - A locked target missed for up to [Config.holdMillis] stays locked, so a single bad frame
 *   (glare, motion blur) does not drop the lock.
 *
 * Not thread-safe: feed it from one analysis thread.
 */
class SingleTargetSelector(private val config: Config = Config()) {

    data class Config(val switchMargin: Float = 1.5f, val framesToLock: Int = 3, val holdMillis: Long = 300) {
        init {
            require(switchMargin >= 1f) { "switchMargin must be at least 1" }
            require(framesToLock >= 1) { "framesToLock must be at least 1" }
            require(holdMillis >= 0) { "holdMillis must not be negative" }
        }
    }

    sealed interface State {
        /** No target. */
        data object Searching : State

        /** A target is chosen but has not been stable long enough to lock. */
        data class Tracking(val target: Detection, val stableFrames: Int, val lastSeenMillis: Long) : State

        /** The target is locked: show its card, copy its number. */
        data class Locked(val target: Detection, val lastSeenMillis: Long) : State
    }

    var state: State = State.Searching
        private set

    fun reset() {
        state = State.Searching
    }

    /** Advances the selector by one analysed frame and returns the new state. */
    fun update(detections: List<Detection>, frame: FrameSize, timestampMillis: Long): State {
        val scored = detections.map { it to score(it, frame) }
        val best = scored.maxByOrNull { it.second }
        val current = state.target()
        val currentNow = current?.let { cur -> scored.firstOrNull { it.first.code == cur.code } }

        state = when {
            current == null -> startTracking(best?.first, timestampMillis)

            currentNow == null -> keepOrDrop(timestampMillis, best?.first)

            best != null && best.first.code != current.code && best.second > currentNow.second * config.switchMargin ->
                startTracking(best.first, timestampMillis)

            else -> advance(currentNow.first, timestampMillis)
        }
        return state
    }

    private fun startTracking(target: Detection?, now: Long): State = when {
        target == null -> State.Searching
        config.framesToLock == 1 -> State.Locked(target, now)
        else -> State.Tracking(target, stableFrames = 1, lastSeenMillis = now)
    }

    private fun advance(target: Detection, now: Long): State = when (val s = state) {
        is State.Locked -> State.Locked(target, now)

        is State.Tracking -> {
            val stable = s.stableFrames + 1
            if (stable >= config.framesToLock) State.Locked(target, now) else State.Tracking(target, stable, now)
        }

        State.Searching -> startTracking(target, now)
    }

    /** The current target is not in this frame: keep it within the hold time, else start over. */
    private fun keepOrDrop(now: Long, best: Detection?): State {
        val lastSeen = when (val s = state) {
            is State.Locked -> s.lastSeenMillis
            is State.Tracking -> s.lastSeenMillis
            State.Searching -> return startTracking(best, now)
        }
        return if (now - lastSeen <= config.holdMillis) state else startTracking(best, now)
    }

    companion object {
        /** How much a label at the left or right edge loses against one on the vertical middle line. */
        const val SIDE_PENALTY = 0.5f

        /**
         * Frame-area share times a horizontal weight, in 0..1. The weight falls linearly from 1 on
         * the vertical middle line to 1 - [SIDE_PENALTY] at the left and right edges.
         */
        fun score(detection: Detection, frame: FrameSize): Float {
            val frameArea = frame.width.toFloat() * frame.height
            val half = frame.width / 2f
            val offset = (abs(detection.center.x - half) / half).coerceIn(0f, 1f)
            return (detection.area / frameArea).coerceIn(0f, 1f) * (1f - SIDE_PENALTY * offset)
        }

        private fun State.target(): Detection? = when (this) {
            is State.Locked -> target
            is State.Tracking -> target
            State.Searching -> null
        }
    }
}
