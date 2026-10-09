// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.recognition

import kotlin.math.abs

/** A point in upright frame coordinates, in pixels. */
data class Point(val x: Float, val y: Float)

/**
 * One decoded label in a frame.
 *
 * [corners] are in upright frame coordinates (after applying the sensor rotation), clockwise
 * from any corner. Decoders report four corners; the polygon is used for both scoring and
 * drawing.
 */
data class Detection(val code: TagCode, val corners: List<Point>) {
    init {
        require(corners.size == CORNERS) { "Expected $CORNERS corners, got ${corners.size}" }
    }

    val center: Point
        get() = Point(
            x = corners.sumOf { it.x.toDouble() }.toFloat() / CORNERS,
            y = corners.sumOf { it.y.toDouble() }.toFloat() / CORNERS,
        )

    /** Polygon area by the shoelace formula. */
    val area: Float
        get() {
            var twice = 0f
            for (i in corners.indices) {
                val a = corners[i]
                val b = corners[(i + 1) % CORNERS]
                twice += a.x * b.y - b.x * a.y
            }
            return abs(twice) / 2
        }

    private companion object {
        const val CORNERS = 4
    }
}

/** Upright size of the analysed frame, in pixels. */
data class FrameSize(val width: Int, val height: Int)
