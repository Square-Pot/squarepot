// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.recognition

import io.github.squarepot.app.recognition.SingleTargetSelector.State
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SingleTargetSelectorTest {
    private val frame = FrameSize(1280, 720)

    /** An axis-aligned square label of [side] px centred at ([x], [y]). */
    private fun tag(code: String, x: Float, y: Float, side: Float = 60f): Detection {
        val h = side / 2
        return Detection(
            requireNotNull(TagCode.parse(code)),
            listOf(Point(x - h, y - h), Point(x + h, y - h), Point(x + h, y + h), Point(x - h, y + h)),
        )
    }

    private val centre = tag("111111", 640f, 360f)
    private val edge = tag("222222", 100f, 100f)

    private fun State.code(): String? = when (this) {
        is State.Locked -> target.code.value
        is State.Tracking -> target.code.value
        State.Searching -> null
    }

    @Test
    fun `score prefers a label near the vertical middle over an equal one at the side`() {
        assertTrue(SingleTargetSelector.score(centre, frame) > SingleTargetSelector.score(edge, frame))
    }

    @Test
    fun `score ignores vertical position`() {
        val onRimAbove = tag("333333", 640f, 80f)
        val onRimBelow = tag("444444", 640f, 650f)
        assertEquals(SingleTargetSelector.score(centre, frame), SingleTargetSelector.score(onRimAbove, frame), 1e-6f)
        assertEquals(SingleTargetSelector.score(centre, frame), SingleTargetSelector.score(onRimBelow, frame), 1e-6f)
    }

    @Test
    fun `size outweighs horizontal position`() {
        val nearAtSide = tag("555555", 100f, 360f, side = 90f)
        assertTrue(SingleTargetSelector.score(nearAtSide, frame) > SingleTargetSelector.score(centre, frame))
    }

    @Test
    fun `score prefers a larger label at the same position`() {
        val big = tag("333333", 640f, 360f, side = 120f)
        assertTrue(SingleTargetSelector.score(big, frame) > SingleTargetSelector.score(centre, frame))
    }

    @Test
    fun `nothing detected stays searching`() {
        val s = SingleTargetSelector()
        assertEquals(State.Searching, s.update(emptyList(), frame, 0))
    }

    @Test
    fun `locks after N consecutive frames`() {
        val s = SingleTargetSelector(SingleTargetSelector.Config(framesToLock = 3))
        assertTrue(s.update(listOf(centre, edge), frame, 0) is State.Tracking)
        assertTrue(s.update(listOf(centre, edge), frame, 33) is State.Tracking)
        val locked = s.update(listOf(centre, edge), frame, 66)
        assertTrue(locked is State.Locked)
        assertEquals("111111", locked.code())
    }

    @Test
    fun `a miss within the hold pauses the lock count instead of resetting it`() {
        val s = SingleTargetSelector(SingleTargetSelector.Config(framesToLock = 3, holdMillis = 300))
        s.update(listOf(centre), frame, 0)
        s.update(listOf(centre), frame, 33)
        val paused = s.update(emptyList(), frame, 66)
        assertTrue(paused is State.Tracking)
        assertEquals(2, (paused as State.Tracking).stableFrames)
        assertTrue(s.update(listOf(centre), frame, 99) is State.Locked)
    }

    @Test
    fun `a miss longer than the hold restarts the lock count`() {
        val s = SingleTargetSelector(SingleTargetSelector.Config(framesToLock = 3, holdMillis = 300))
        s.update(listOf(centre), frame, 0)
        s.update(listOf(centre), frame, 33)
        assertEquals(State.Searching, s.update(emptyList(), frame, 400))
        val restarted = s.update(listOf(centre), frame, 433)
        assertEquals(1, (restarted as State.Tracking).stableFrames)
    }

    @Test
    fun `a neighbour scoring slightly higher does not steal the target`() {
        val s = SingleTargetSelector(SingleTargetSelector.Config(switchMargin = 1.5f, framesToLock = 1))
        s.update(listOf(centre), frame, 0)
        // The neighbour is a bit larger (scores ~1.2x higher) but below the switch margin.
        val neighbour = tag("444444", 700f, 360f, side = 68f)
        assertEquals("111111", s.update(listOf(centre, neighbour), frame, 33).code())
    }

    @Test
    fun `a clearly better label takes over and restarts the lock count`() {
        val s = SingleTargetSelector(SingleTargetSelector.Config(framesToLock = 2))
        s.update(listOf(edge), frame, 0)
        s.update(listOf(edge), frame, 33)
        val switched = s.update(listOf(edge, centre), frame, 66)
        assertTrue(switched is State.Tracking)
        assertEquals("111111", switched.code())
    }

    @Test
    fun `a lock survives a short dropout and is lost after the hold time`() {
        val s = SingleTargetSelector(SingleTargetSelector.Config(framesToLock = 1, holdMillis = 300))
        s.update(listOf(centre), frame, 0)
        assertTrue(s.update(emptyList(), frame, 200) is State.Locked)
        assertTrue(s.update(emptyList(), frame, 300) is State.Locked)
        assertEquals(State.Searching, s.update(emptyList(), frame, 301))
    }

    @Test
    fun `during the hold another label does not replace the locked one`() {
        val s = SingleTargetSelector(SingleTargetSelector.Config(framesToLock = 1, holdMillis = 300))
        s.update(listOf(centre), frame, 0)
        assertEquals("111111", s.update(listOf(edge), frame, 100).code())
        assertEquals("222222", s.update(listOf(edge), frame, 400).code())
    }

    @Test
    fun `the locked target follows the label as it moves`() {
        val s = SingleTargetSelector(SingleTargetSelector.Config(framesToLock = 1))
        s.update(listOf(centre), frame, 0)
        val moved = tag("111111", 660f, 370f)
        val state = s.update(listOf(moved), frame, 33) as State.Locked
        assertEquals(moved.center, state.target.center)
    }
}
