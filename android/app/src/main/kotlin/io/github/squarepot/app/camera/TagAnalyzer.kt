package io.github.squarepot.app.camera

import android.os.SystemClock
import android.util.Log
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import io.github.squarepot.app.decoder.DecoderInput
import io.github.squarepot.app.decoder.TagDecoder
import io.github.squarepot.app.recognition.Detection
import io.github.squarepot.app.recognition.FrameSize

/** What one decoder found in one camera frame. */
class FrameResult(
    val decoderId: String,
    val detections: List<Detection>,
    val frame: FrameSize,
    val decodeMillis: Float,
    val timestampMillis: Long,
)

/** Runs the decoder chosen for each frame and hands the result on, on the analysis thread. */
class TagAnalyzer(private val nextDecoder: () -> TagDecoder, private val onFrame: (FrameResult) -> Unit) :
    ImageAnalysis.Analyzer {

    override fun analyze(image: ImageProxy) {
        image.use {
            val decoder = nextDecoder()
            val input = DecoderInput.Camera(it)
            val start = SystemClock.elapsedRealtimeNanos()
            val detections = runCatching { decoder.decode(input) }
                .onFailure { e -> Log.w(TAG, "${decoder.id} failed on a frame", e) }
                .getOrDefault(emptyList())
            val millis = (SystemClock.elapsedRealtimeNanos() - start) / NANOS_PER_MILLI
            onFrame(
                FrameResult(
                    decoderId = decoder.id,
                    detections = detections,
                    frame = input.uprightSize,
                    decodeMillis = millis,
                    timestampMillis = it.imageInfo.timestamp / NANOS_PER_MILLI.toLong(),
                ),
            )
        }
    }

    private companion object {
        const val TAG = "TagAnalyzer"
        const val NANOS_PER_MILLI = 1_000_000f
    }
}
