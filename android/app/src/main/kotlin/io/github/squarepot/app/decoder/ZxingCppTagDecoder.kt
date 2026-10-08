package io.github.squarepot.app.decoder

import io.github.squarepot.app.recognition.Detection
import io.github.squarepot.app.recognition.Point
import io.github.squarepot.app.recognition.TagCode
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
        return results.mapNotNull { r ->
            val code = TagCode.parse(r.text)
            if (r.error != null || code == null) {
                null
            } else {
                val p = r.position
                val corners = listOf(p.topLeft, p.topRight, p.bottomRight, p.bottomLeft)
                Detection(code, corners.map { Point(it.x.toFloat(), it.y.toFloat()) })
            }
        }
    }

    override fun close() = Unit
}
