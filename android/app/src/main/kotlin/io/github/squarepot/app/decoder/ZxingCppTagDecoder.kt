package io.github.squarepot.app.decoder

import io.github.squarepot.app.recognition.Detection
import io.github.squarepot.app.recognition.Point
import io.github.squarepot.app.recognition.TagCode
import io.github.squarepot.app.recognition.uprightCropOrigin
import zxingcpp.BarcodeReader

/**
 * zxing-cpp, Data Matrix only.
 *
 * Options follow the host benchmark (#58 report): rotation search is required for Data Matrix,
 * downscaling is nearly free and helps large noisy symbols, inversion is not needed for
 * dark-on-light labels and doubles the time.
 */
class ZxingCppTagDecoder : TagDecoder {
    override val id = "zxing-cpp"

    private val reader = BarcodeReader(
        BarcodeReader.Options(
            formats = setOf(BarcodeReader.Format.DATA_MATRIX),
            tryRotate = true,
            tryDownscale = true,
            tryInvert = false,
        ),
    )

    override fun decode(input: DecoderInput): List<Detection> {
        val results = when (input) {
            is DecoderInput.Camera -> reader.read(input.image)
            is DecoderInput.Still -> reader.read(input.bitmap)
        }
        // Positions are relative to the frame's crop rect; move them back into the whole frame.
        val origin = when (input) {
            is DecoderInput.Camera -> with(input.image) {
                uprightCropOrigin(
                    cropRect.left,
                    cropRect.top,
                    cropRect.right,
                    cropRect.bottom,
                    width,
                    height,
                    imageInfo.rotationDegrees,
                )
            }

            is DecoderInput.Still -> Point(0f, 0f)
        }
        return results.mapNotNull { r ->
            val code = TagCode.parse(r.text)
            if (r.error != null || code == null) {
                null
            } else {
                val p = r.position
                val corners = listOf(p.topLeft, p.topRight, p.bottomRight, p.bottomLeft)
                Detection(code, corners.map { Point(origin.x + it.x, origin.y + it.y) })
            }
        }
    }

    override fun close() = Unit
}
