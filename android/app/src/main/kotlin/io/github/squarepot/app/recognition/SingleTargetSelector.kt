package io.github.squarepot.app.recognition

import kotlin.math.hypot

/**
 * Picks the one label the user is aiming at, frame by frame, for the single-plant mode.
 *
 * - Each detection is scored by its share of the frame area times its proximity to the centre,
 *   so a large label near the crosshair wins over a small one at the edge.
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
        /**
         * Frame-area share times centre proximity, in 0..1. Proximity falls linearly from 1 at the
         * centre to 0 at the corners.
         */
        fun score(detection: Detection, frame: FrameSize): Float {
            val frameArea = frame.width.toFloat() * frame.height
            val cx = frame.width / 2f
            val cy = frame.height / 2f
            val maxDistance = hypot(cx, cy)
            val c = detection.center
            val proximity = (1f - hypot(c.x - cx, c.y - cy) / maxDistance).coerceIn(0f, 1f)
            return (detection.area / frameArea).coerceIn(0f, 1f) * proximity
        }

        private fun State.target(): Detection? = when (this) {
            is State.Locked -> target
            is State.Tracking -> target
            State.Searching -> null
        }
    }
}
