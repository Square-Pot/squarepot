// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.recognition

import org.junit.Assert.assertEquals
import org.junit.Test

class CropOriginTest {
    // A 1280x720 buffer cropped top and bottom to a 2.14:1 preview, as on a portrait phone.
    private val crop = intArrayOf(0, 61, 1280, 658)

    private fun origin(rotation: Int, l: Int = crop[0], t: Int = crop[1], r: Int = crop[2], b: Int = crop[3]) =
        uprightCropOrigin(l, t, r, b, width = 1280, height = 720, rotationDegrees = rotation)

    @Test
    fun `an uncropped frame has its origin at zero in every rotation`() {
        listOf(0, 90, 180, 270).forEach {
            assertEquals("rotation $it", Point(0f, 0f), origin(it, 0, 0, 1280, 720))
        }
    }

    @Test
    fun `landscape keeps the buffer offset`() {
        assertEquals(Point(0f, 61f), origin(0))
    }

    @Test
    fun `portrait moves the cut-off bottom rows to the left edge`() {
        // Turned clockwise, buffer row y becomes upright column 719 - y, so the 62 rows below
        // the crop end up left of it.
        assertEquals(Point(62f, 0f), origin(90))
    }

    @Test
    fun `upside down and reverse portrait mirror the other two`() {
        assertEquals(Point(0f, 62f), origin(180))
        assertEquals(Point(61f, 0f), origin(270))
    }

    @Test
    fun `a crop off one corner lands where that corner goes`() {
        // Crop the buffer's right half; upright after 90 degrees that is the bottom half.
        assertEquals(Point(0f, 640f), origin(90, 640, 0, 1280, 720))
    }

    @Test(expected = IllegalArgumentException::class)
    fun `other rotations are rejected`() {
        origin(45)
    }
}
