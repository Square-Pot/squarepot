package io.github.squarepot.app.decoder

import android.graphics.Bitmap
import androidx.camera.core.ImageProxy
import io.github.squarepot.app.recognition.Detection
import io.github.squarepot.app.recognition.FrameSize

/** An image to decode: a live camera frame or a still photo. */
sealed interface DecoderInput {
    /** Upright size; detections are reported in this coordinate system. */
    val uprightSize: FrameSize

    class Camera(val image: ImageProxy) : DecoderInput {
        override val uprightSize: FrameSize
            get() = when (image.imageInfo.rotationDegrees) {
                90, 270 -> FrameSize(image.height, image.width)
                else -> FrameSize(image.width, image.height)
            }
    }

    class Still(val bitmap: Bitmap) : DecoderInput {
        override val uprightSize: FrameSize
            get() = FrameSize(bitmap.width, bitmap.height)
    }
}

/** Finds label Data Matrix symbols in an image. Only valid six-digit labels are returned. */
interface TagDecoder : AutoCloseable {
    /** Stable id, used in bench results. */
    val id: String

    /** Blocks until decoded. Call from a background thread. */
    fun decode(input: DecoderInput): List<Detection>
}
