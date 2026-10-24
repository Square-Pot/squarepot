// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import io.github.squarepot.app.SquarepotApplication
import io.github.squarepot.app.data.PlantView
import io.github.squarepot.app.decoder.TagDecoder
import io.github.squarepot.app.decoder.ZxingCppTagDecoder
import io.github.squarepot.app.recognition.CornerSmoother
import io.github.squarepot.app.recognition.Detection
import io.github.squarepot.app.recognition.DetectionHold
import io.github.squarepot.app.recognition.FrameSize
import io.github.squarepot.app.recognition.RollingStats
import io.github.squarepot.app.recognition.SingleTargetSelector
import io.github.squarepot.app.recognition.TagCode
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.Locale

data class CameraUiState(
    val resolution: AnalysisResolution = AnalysisResolution.P720,
    val frame: FrameSize? = null,
    /**
     * The labels to draw: this frame's and those missed for no longer than the hold time, with
     * smoothed corners.
     */
    val detections: List<Detection> = emptyList(),
    val selection: SingleTargetSelector.State = SingleTargetSelector.State.Searching,
    /** The label pinned by a tap, if any; the overlay draws it in its own colour. */
    val pinned: TagCode? = null,
    /** Plants in the local copy by label number, for the labels looked up so far. */
    val plants: Map<String, List<PlantView>> = emptyMap(),
    val stats: Map<String, RollingStats.Snapshot> = emptyMap(),
)

/**
 * Live single-plant recognition. [decoder] and [onFrame] are used on the camera analysis thread;
 * everything the UI reads goes through [state].
 */
class CameraViewModel(application: Application) : AndroidViewModel(application) {
    private val container = (application as SquarepotApplication).container
    val decoder: TagDecoder = ZxingCppTagDecoder()
    private val selector = SingleTargetSelector()
    private val hold = DetectionHold()
    private val smoother = CornerSmoother()
    private val stats = RollingStats()

    private val _state = MutableStateFlow(CameraUiState())
    val state: StateFlow<CameraUiState> = _state.asStateFlow()

    private val lookup = TagLookup(
        viewModelScope,
        lookup = { container.localCopy.plantsByTag(it, Locale.getDefault().language) },
        onResult = { publishPlants() },
    )

    @Volatile
    private var resetRequested = false

    @Volatile
    private var pendingTap: SingleTargetSelector.Tap? = null

    init {
        // A refreshed copy or a new schema can change any answer: look the labels up again.
        viewModelScope.launch {
            container.database.copy().observeState()
                .map { it?.refreshedAt to it?.schemaVersion }
                .distinctUntilChanged()
                .collect {
                    lookup.invalidate()
                    publishPlants()
                }
        }
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

    fun onFrame(result: FrameResult) {
        if (resetRequested) {
            resetRequested = false
            selector.reset()
            hold.clear()
            smoother.clear()
            stats.clear()
        }
        stats.add(result.decodeMillis, hit = result.detections.isNotEmpty())
        val tap = pendingTap
        pendingTap = null
        val selection = selector.update(result.detections, result.frame, result.timestampMillis, tap)
        val shown = hold.update(result.detections, result.timestampMillis)
        lookup.request(shown.map { it.code.value })
        val drawn = smoother.update(shown, result.detections, result.timestampMillis)
        _state.update {
            it.copy(
                frame = result.frame,
                detections = drawn,
                selection = selection,
                pinned = selector.pinned,
                stats = mapOf(result.decoderId to stats.snapshot()),
            )
        }
    }

    private fun publishPlants() {
        _state.update { it.copy(plants = lookup.results) }
    }

    override fun onCleared() {
        decoder.close()
    }
}
