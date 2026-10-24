// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import androidx.lifecycle.ViewModel
import io.github.squarepot.app.decoder.MlKitTagDecoder
import io.github.squarepot.app.decoder.TagDecoder
import io.github.squarepot.app.decoder.ZxingCppTagDecoder
import io.github.squarepot.app.recognition.Detection
import io.github.squarepot.app.recognition.FrameSize
import io.github.squarepot.app.recognition.RollingStats
import io.github.squarepot.app.recognition.SingleTargetSelector
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

/** Which decoder runs on live frames. [ALTERNATE] runs both on every other frame, to compare them. */
enum class DecoderMode { MLKIT, ZXING_CPP, ALTERNATE }

data class CameraUiState(
    val mode: DecoderMode = DecoderMode.MLKIT,
    val resolution: AnalysisResolution = AnalysisResolution.P720,
    val frame: FrameSize? = null,
    val detections: List<Detection> = emptyList(),
    val selection: SingleTargetSelector.State = SingleTargetSelector.State.Searching,
    val stats: Map<String, RollingStats.Snapshot> = emptyMap(),
)

/**
 * Live single-plant recognition. [onFrame] and [nextDecoder] are called on the camera analysis
 * thread; everything the UI reads goes through [state].
 */
class CameraViewModel : ViewModel() {
    private val mlKit = MlKitTagDecoder()
    private val zxing = ZxingCppTagDecoder()
    private val selector = SingleTargetSelector()
    private val stats = mapOf(mlKit.id to RollingStats(), zxing.id to RollingStats())

    private val _state = MutableStateFlow(CameraUiState())
    val state: StateFlow<CameraUiState> = _state.asStateFlow()

    @Volatile
    private var resetRequested = false

    @Volatile
    private var pendingTap: SingleTargetSelector.Tap? = null
    private var frameIndex = 0L

    fun setMode(mode: DecoderMode) {
        if (mode == _state.value.mode) return
        resetRequested = true
        _state.update { it.copy(mode = mode) }
    }

    fun setResolution(resolution: AnalysisResolution) {
        if (resolution == _state.value.resolution) return
        resetRequested = true
        _state.update { it.copy(resolution = resolution) }
    }

    /** A tap on the preview; the selector takes it with the next frame. */
    fun tap(tap: SingleTargetSelector.Tap) {
        pendingTap = tap
    }

    fun nextDecoder(): TagDecoder = when (_state.value.mode) {
        DecoderMode.MLKIT -> mlKit
        DecoderMode.ZXING_CPP -> zxing
        DecoderMode.ALTERNATE -> if (frameIndex % 2 == 0L) mlKit else zxing
    }

    fun onFrame(result: FrameResult) {
        frameIndex++
        // A frame decoded just before a mode switch belongs to the old mode: drop it.
        if (result.decoderId !in decoderIds(_state.value.mode)) return
        if (resetRequested) {
            resetRequested = false
            selector.reset()
            stats.values.forEach { it.clear() }
        }
        stats.getValue(result.decoderId).add(result.decodeMillis, hit = result.detections.isNotEmpty())
        val tap = pendingTap
        pendingTap = null
        val selection = selector.update(result.detections, result.frame, result.timestampMillis, tap)
        _state.update {
            it.copy(
                frame = result.frame,
                detections = result.detections,
                selection = selection,
                stats = stats.mapValues { (_, s) -> s.snapshot() },
            )
        }
    }

    private fun decoderIds(mode: DecoderMode): Set<String> = when (mode) {
        DecoderMode.MLKIT -> setOf(mlKit.id)
        DecoderMode.ZXING_CPP -> setOf(zxing.id)
        DecoderMode.ALTERNATE -> setOf(mlKit.id, zxing.id)
    }

    override fun onCleared() {
        mlKit.close()
        zxing.close()
    }
}
