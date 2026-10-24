// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CaptionPlacementTest {
    // A phone-sized view less a top bar and the bottom label count, a 184 × 90 card, a 19 px tab.
    private val area = ViewBox(0f, 76f, 330f, 677f)
    private val placement = CaptionPlacement(tabHeight = 19f, gap = 6f)

    private fun place(label: ViewBox) = placement.place(label, cardWidth = 184f, cardHeight = 90f, area = area)

    @Test
    fun `the caption goes to the right when it fits, its tab level with the label's top`() {
        val spot = place(ViewBox(40f, 300f, 80f, 340f))
        assertEquals(CaptionSide.RIGHT, spot.side)
        assertEquals(ViewBox(86f, 281f, 270f, 371f), spot.box)
    }

    @Test
    fun `without room on the right it goes above, its bottom on the label's top`() {
        val spot = place(ViewBox(200f, 300f, 240f, 340f))
        assertEquals(CaptionSide.ABOVE, spot.side)
        assertEquals(300f, spot.box.bottom)
        assertEquals(146f, spot.box.left)
    }

    @Test
    fun `a caption above stays inside the view on the left`() {
        val spot = placement.place(ViewBox(-10f, 300f, 30f, 340f), cardWidth = 340f, cardHeight = 90f, area = area)
        assertEquals(CaptionSide.ABOVE, spot.side)
        assertEquals(0f, spot.box.left)
    }

    @Test
    fun `a caption never goes below its label`() {
        for (y in listOf(80f, 200f, 400f, 600f)) {
            for (x in listOf(0f, 100f, 200f, 290f)) {
                val label = ViewBox(x, y, x + 40f, y + 40f)
                assertTrue("label at $x,$y", place(label).box.top < label.bottom)
            }
        }
    }

    @Test
    fun `near the top edge the caption is pushed down into the view`() {
        val spot = place(ViewBox(200f, 90f, 240f, 130f))
        assertEquals(CaptionSide.ABOVE, spot.side)
        assertEquals(76f, spot.box.top)
    }

    @Test
    fun `a neighbour keeps its name, then only its number, then nothing as room runs out`() {
        val caption = ViewBox(100f, 100f, 200f, 200f)
        val name = ViewBox(20f, 150f, 120f, 169f)
        val number = ViewBox(20f, 150f, 70f, 169f)
        assertEquals(NeighbourTab.NUMBER_AND_NAME, CaptionPlacement.neighbourTab(name, number, emptyList()))
        assertEquals(NeighbourTab.NUMBER, CaptionPlacement.neighbourTab(name, number, listOf(caption)))
        assertEquals(NeighbourTab.NUMBER, CaptionPlacement.neighbourTab(null, number, listOf(caption)))
        val bigger = ViewBox(0f, 140f, 80f, 180f)
        assertEquals(NeighbourTab.HIDDEN, CaptionPlacement.neighbourTab(name, number, listOf(bigger)))
    }

    @Test
    fun `boxes that only touch do not overlap`() {
        assertTrue(!ViewBox(0f, 0f, 10f, 10f).overlaps(ViewBox(10f, 0f, 20f, 10f)))
        assertTrue(ViewBox(0f, 0f, 10f, 10f).overlaps(ViewBox(9f, 9f, 20f, 20f)))
    }
}
