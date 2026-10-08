package io.github.squarepot.app.decoder

import androidx.annotation.OptIn
import androidx.camera.core.ExperimentalGetImage
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import io.github.squarepot.app.recognition.Detection
import io.github.squarepot.app.recognition.Point
import io.github.squarepot.app.recognition.TagCode

/** ML Kit Barcode Scanning with the bundled model, Data Matrix only. */
class MlKitTagDecoder : TagDecoder {
    override val id = "mlkit"

    private val scanner = BarcodeScanning.getClient(
        BarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_DATA_MATRIX).build(),
    )

    @OptIn(ExperimentalGetImage::class)
    override fun decode(input: DecoderInput): List<Detection> {
        val image = when (input) {
            is DecoderInput.Camera -> InputImage.fromMediaImage(
                requireNotNull(input.image.image) { "ImageProxy without an image" },
                input.image.imageInfo.rotationDegrees,
            )

            is DecoderInput.Still -> InputImage.fromBitmap(input.bitmap, 0)
        }
        return Tasks.await(scanner.process(image)).mapNotNull { it.toDetection() }
    }

    override fun close() = scanner.close()

    private fun Barcode.toDetection(): Detection? {
        val code = TagCode.parse(rawValue)
        val corners = cornerPoints?.takeIf { it.size == CORNERS }
        return if (code == null || corners == null) {
            null
        } else {
            Detection(code, corners.map { Point(it.x.toFloat(), it.y.toFloat()) })
        }
    }

    private companion object {
        const val CORNERS = 4
    }
}
