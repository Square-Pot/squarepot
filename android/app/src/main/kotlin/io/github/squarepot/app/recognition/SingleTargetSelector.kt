// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.recognition

import kotlin.math.hypot
import kotlin.math.sqrt

/**
 * Picks the one label to show, frame by frame, for the single-plant mode. In order:
 *
 * 1. **A tap wins.** A tap on a label pins it, whatever its size, and locks it at once. The pin
 *    is released by a tap on another label (which is pinned instead), a tap where there is no
 *    label, or the pinned label being missed for longer than [Config.holdMillis].
 * 2. **Otherwise the clearly largest label**, which is the nearest pot's. Labels more than
 *    [Config.sizeTie] times smaller than the largest are background and never chosen.
 * 3. **Among labels of about equal size, the one nearest the aim point**: centred horizontally,
 *    [Config.aimY] of the way down the frame, with vertical distance counting [Config.verticalWeight]
 *    as much as horizontal. The plant fills the middle of the frame and its label usually sits on
 *    the far rim, above it, so a label above the centre is not pushed aside by one beside it.
 *
 * - Hysteresis: once a target is chosen automatically, another label of about equal size replaces
 *   it only when it is [Config.switchMargin] times nearer the aim point, so the target does not
 *   flicker between neighbours. A clearly larger label replaces it at once.
 * - A target is locked after [Config.framesToLock] frames in which it was seen and chosen.
 *   Frames where the decoder misses it for no longer than [Config.holdMillis] neither count nor
 *   reset the count; a longer gap, or another label taking over, starts over.
 * - A locked target missed for up to [Config.holdMillis] stays locked, so a single bad frame
 *   (glare, motion blur) does not drop the lock.
 *
 * Not thread-safe: feed it from one analysis thread.
 */
class SingleTargetSelector(private val config: Config = Config()) {

    data class Config(
        val sizeTie: Float = 1.5f,
        val switchMargin: Float = 1.5f,
        val framesToLock: Int = 3,
        val holdMillis: Long = 300,
        val aimY: Float = AIM_Y,
        val verticalWeight: Float = 0.5f,
    ) {
        init {
            require(sizeTie >= 1f) { "sizeTie must be at least 1" }
            require(switchMargin >= 1f) { "switchMargin must be at least 1" }
            require(framesToLock >= 1) { "framesToLock must be at least 1" }
            require(holdMillis >= 0) { "holdMillis must not be negative" }
            require(aimY in 0f..1f) { "aimY must be within the frame" }
            require(verticalWeight >= 0f) { "verticalWeight must not be negative" }
        }
    }

    /** A tap on the preview in upright frame coordinates; [radius] is the finger's reach in frame pixels. */
    data class Tap(val point: Point, val radius: Float)

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

    /** The label pinned by a tap, if any. */
    var pinned: TagCode? = null
        private set

    fun reset() {
        state = State.Searching
        pinned = null
    }

    /** Advances the selector by one analysed frame, and any tap since the last one, and returns the new state. */
    fun update(detections: List<Detection>, frame: FrameSize, timestampMillis: Long, tap: Tap? = null): State {
        if (tap != null) {
            val hit = detections.filter { it.isHit(tap) }.minByOrNull { distance(it.center, tap.point) }
            pinned = hit?.code
            if (hit != null) {
                state = State.Locked(hit, timestampMillis)
                return state
            }
        }
        state = pinned?.let { followPin(it, detections, frame, timestampMillis) }
            ?: chooseAutomatically(detections, frame, timestampMillis)
        return state
    }

    /** The pinned label stays locked while it is seen or within the hold time; after that the pin is released. */
    private fun followPin(code: TagCode, detections: List<Detection>, frame: FrameSize, now: Long): State {
        val seen = detections.firstOrNull { it.code == code }
        return when {
            seen != null -> State.Locked(seen, now)

            now - lastSeen() <= config.holdMillis -> state

            else -> {
                pinned = null
                startTracking(candidates(detections).minByOrNull { aimDistance(it, frame) }, now)
            }
        }
    }

    private fun chooseAutomatically(detections: List<Detection>, frame: FrameSize, now: Long): State {
        val candidates = candidates(detections)
        val best = candidates.minByOrNull { aimDistance(it, frame) }
        val current = state.target()
        val currentNow = current?.let { cur -> detections.firstOrNull { it.code == cur.code } }

        return when {
            current == null -> startTracking(best, now)

            currentNow == null -> keepOrDrop(now, best)

            currentNow !in candidates -> startTracking(best, now)

            best != null &&
                best.code != current.code &&
                aimDistance(best, frame) * config.switchMargin < aimDistance(currentNow, frame) ->
                startTracking(best, now)

            else -> advance(currentNow, now)
        }
    }

    /** The labels about as large as the largest one. */
    private fun candidates(detections: List<Detection>): List<Detection> {
        val largest = detections.maxOfOrNull { it.area } ?: return emptyList()
        return detections.filter { it.area * config.sizeTie >= largest }
    }

    private fun aimDistance(detection: Detection, frame: FrameSize): Float {
        val aim = aimPoint(frame, config)
        val c = detection.center
        return hypot(c.x - aim.x, (c.y - aim.y) * config.verticalWeight)
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
    private fun keepOrDrop(now: Long, best: Detection?): State =
        if (now - lastSeen() <= config.holdMillis) state else startTracking(best, now)

    private fun lastSeen(): Long = when (val s = state) {
        is State.Locked -> s.lastSeenMillis
        is State.Tracking -> s.lastSeenMillis
        State.Searching -> Long.MIN_VALUE / 2
    }

    companion object {
        /** Default height of the aim point, as a share of the frame height from the top. */
        const val AIM_Y = 0.4f

        /** Where the selector aims in [frame]; the preview draws its centre mark there. */
        fun aimPoint(frame: FrameSize, config: Config = Config()) = Point(frame.width / 2f, frame.height * config.aimY)

        private fun State.target(): Detection? = when (this) {
            is State.Locked -> target
            is State.Tracking -> target
            State.Searching -> null
        }
    }
}

/** Whether [tap] lands on this label or within the finger's reach of it. */
fun Detection.isHit(tap: SingleTargetSelector.Tap): Boolean = distance(center, tap.point) <= tap.radius + sqrt(area) / 2

private fun distance(a: Point, b: Point) = hypot(a.x - b.x, a.y - b.y)
