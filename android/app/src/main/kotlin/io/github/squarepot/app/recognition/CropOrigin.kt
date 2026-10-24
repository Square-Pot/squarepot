// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.recognition

/**
 * Where the top-left corner of a crop lands once the frame is turned upright.
 *
 * zxing-cpp decodes only a camera frame's crop rect (CameraController sets it to the preview's
 * aspect ratio) and reports positions relative to the upright crop; adding this origin puts them
 * in upright frame coordinates. [left], [top], [right] and [bottom] are the crop in sensor
 * buffer pixels, [width] and [height] the buffer size, [rotationDegrees] the clockwise rotation
 * that makes the buffer upright.
 */
@Suppress("LongParameterList")
fun uprightCropOrigin(
    left: Int,
    top: Int,
    right: Int,
    bottom: Int,
    width: Int,
    height: Int,
    rotationDegrees: Int,
): Point = when (rotationDegrees) {
    0 -> Point(left.toFloat(), top.toFloat())
    QUARTER_TURN -> Point((height - bottom).toFloat(), left.toFloat())
    HALF_TURN -> Point((width - right).toFloat(), (height - bottom).toFloat())
    THREE_QUARTER_TURN -> Point(top.toFloat(), (width - right).toFloat())
    else -> throw IllegalArgumentException("Rotation must be 0, 90, 180 or 270, got $rotationDegrees")
}

private const val QUARTER_TURN = 90
private const val HALF_TURN = 180
private const val THREE_QUARTER_TURN = 270
