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

    private fun pick(vararg detections: Detection): String? =
        SingleTargetSelector(SingleTargetSelector.Config(framesToLock = 1)).update(detections.toList(), frame, 0).code()

    private fun tapAt(x: Float, y: Float) = SingleTargetSelector.Tap(Point(x, y), radius = 40f)

    @Test
    fun `a clearly larger label wins wherever it is`() {
        val nearAtSide = tag("555555", 100f, 600f, side = 90f)
        assertEquals("555555", pick(centre, nearAtSide))
    }

    @Test
    fun `among labels of about equal size the one nearest the aim point wins`() {
        val aside = tag("333333", 1000f, 360f, side = 66f)
        assertEquals("111111", pick(aside, centre))
    }

    @Test
    fun `a label on the rim above the plant beats an equal one beside it`() {
        // The aim point sits above the centre and vertical distance counts half.
        val onRimAbove = tag("333333", 640f, 120f)
        val beside = tag("444444", 820f, 360f)
        assertEquals("333333", pick(beside, onRimAbove))
    }

    @Test
    fun `the aim point is centred and a bit above the middle`() {
        assertEquals(Point(640f, 288f), SingleTargetSelector.aimPoint(frame))
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
        // The neighbour is a bit larger and only a little farther from the aim point.
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

    @Test
    fun `a tap pins a smaller label at once and it stays chosen`() {
        val s = SingleTargetSelector(SingleTargetSelector.Config(framesToLock = 3))
        val big = tag("555555", 640f, 300f, side = 120f)
        s.update(listOf(big, edge), frame, 0)
        val tapped = s.update(listOf(big, edge), frame, 33, tapAt(110f, 95f))
        assertTrue(tapped is State.Locked)
        assertEquals("222222", tapped.code())
        assertEquals("222222", s.update(listOf(big, edge), frame, 66).code())
        assertEquals("222222", s.pinned?.value)
    }

    @Test
    fun `a tap just beside a label still reaches it`() {
        val s = SingleTargetSelector()
        // 30 px beyond the label's edge, within the 40 px reach.
        assertEquals("222222", s.update(listOf(centre, edge), frame, 0, tapAt(100f, 160f)).code())
    }

    @Test
    fun `a tap on another label moves the pin`() {
        val s = SingleTargetSelector()
        s.update(listOf(centre, edge), frame, 0, tapAt(100f, 100f))
        assertEquals("111111", s.update(listOf(centre, edge), frame, 33, tapAt(640f, 360f)).code())
        assertEquals("111111", s.pinned?.value)
    }

    @Test
    fun `a tap where there is no label releases the pin`() {
        val s = SingleTargetSelector(SingleTargetSelector.Config(framesToLock = 1))
        s.update(listOf(centre, edge), frame, 0, tapAt(100f, 100f))
        s.update(listOf(centre, edge), frame, 33, tapAt(1200f, 650f))
        assertEquals(null, s.pinned)
        // Automatic choice again: the label nearest the aim point takes over.
        assertEquals("111111", s.update(listOf(centre, edge), frame, 66).code())
    }

    @Test
    fun `a pinned label survives a short dropout and is released after the hold time`() {
        val s = SingleTargetSelector(SingleTargetSelector.Config(framesToLock = 1, holdMillis = 300))
        s.update(listOf(centre, edge), frame, 0, tapAt(100f, 100f))
        assertEquals("222222", s.update(listOf(centre), frame, 200).code())
        assertEquals("111111", s.update(listOf(centre), frame, 400).code())
        assertEquals(null, s.pinned)
    }

    @Test
    fun `reset releases the pin`() {
        val s = SingleTargetSelector()
        s.update(listOf(edge), frame, 0, tapAt(100f, 100f))
        s.reset()
        assertEquals(null, s.pinned)
        assertEquals(State.Searching, s.state)
    }
}
