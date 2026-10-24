// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

/** An axis-aligned box in view pixels. */
data class ViewBox(val left: Float, val top: Float, val right: Float, val bottom: Float) {
    val width get() = right - left
    val height get() = bottom - top

    fun overlaps(other: ViewBox) = left < other.right && other.left < right && top < other.bottom && other.top < bottom

    companion object {
        fun of(left: Float, top: Float, width: Float, height: Float) = ViewBox(left, top, left + width, top + height)
    }
}

/** Where a caption hangs off its label. */
enum class CaptionSide {
    /** To the right, its number tab on the label's top right corner. */
    RIGHT,

    /** Above, its number tab at the bottom touching the label's top. */
    ABOVE,
}

data class CaptionSpot(val box: ViewBox, val side: CaptionSide)

/** What a neighbouring label's number tab can show without touching the caption or an earlier tab. */
enum class NeighbourTab { NUMBER_AND_NAME, NUMBER, HIDDEN }

/**
 * Where captions at the label go (owner, 2026-10-25): to the right of the label when the card
 * fits there, else above it; never below, where the plant usually is, since a label stands above
 * or behind its plant. A card that would leave the area is pushed back inside it, so near the top
 * edge it may come down over its own label, but not under it.
 *
 * [tabHeight] is the number tab's height: the card's top row on the right, its bottom row above.
 * [gap] is the space between the frame and a card on its right. Both in view pixels.
 */
class CaptionPlacement(private val tabHeight: Float, private val gap: Float) {
    /** The spot for a [cardWidth] × [cardHeight] caption at [label] (its frame), inside [area]. */
    fun place(label: ViewBox, cardWidth: Float, cardHeight: Float, area: ViewBox): CaptionSpot {
        val right = label.right + gap
        val spot = if (right + cardWidth <= area.right) {
            ViewBox.of(right, label.top - tabHeight, cardWidth, cardHeight) to CaptionSide.RIGHT
        } else {
            val left = label.left.coerceIn(area.left, maxOf(area.left, area.right - cardWidth))
            ViewBox.of(left, label.top - cardHeight, cardWidth, cardHeight) to CaptionSide.ABOVE
        }
        val (box, side) = spot
        val top = box.top.coerceIn(area.top, maxOf(area.top, area.bottom - cardHeight))
        return CaptionSpot(ViewBox.of(box.left, top, cardWidth, cardHeight), side)
    }

    companion object {
        /**
         * What a neighbour's tab shows: with its short name when [withName] (the tab with the
         * name) touches nothing in [taken], else the number alone when [numberOnly] touches
         * nothing, else nothing. Callers add each tab they draw to [taken], biggest labels first.
         */
        fun neighbourTab(withName: ViewBox?, numberOnly: ViewBox, taken: List<ViewBox>): NeighbourTab = when {
            withName != null && taken.none { it.overlaps(withName) } -> NeighbourTab.NUMBER_AND_NAME
            taken.none { it.overlaps(numberOnly) } -> NeighbourTab.NUMBER
            else -> NeighbourTab.HIDDEN
        }
    }
}
