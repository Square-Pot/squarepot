// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import io.github.squarepot.app.SquarepotApplication
import io.github.squarepot.app.data.CaptionField
import io.github.squarepot.app.data.CaptionSettings
import io.github.squarepot.app.data.PlantView
import io.github.squarepot.app.data.api.FieldSchemaDto
import io.github.squarepot.app.data.local.CollectionColumns
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
    /** The overlay's 1€ filter settings, adjustable from the hidden tuning panel. */
    val smoothing: CornerSmoother.Params = CornerSmoother.Params(),
    /** Plants in the local copy by label number, for the labels looked up so far. */
    val plants: Map<String, List<PlantView>> = emptyMap(),
    val stats: Map<String, RollingStats.Snapshot> = emptyMap(),
    val captions: CaptionSettings = CaptionSettings(),
    /** The copy's field schema, for the captions' display rules; null before the first sync. */
    val schema: FieldSchemaDto? = null,
    /** Each collection's custom columns. */
    val customColumns: List<CollectionColumns> = emptyList(),
    /** When the local copy was last refreshed, epoch millis; null before the first sync. */
    val refreshedAt: Long? = null,
) {
    /**
     * The selected label, with its smoothed corners when it is on screen: locked by the selector
     * or pinned by a tap. A label the selector is still making sure of is not selected yet.
     */
    val selected: Detection?
        get() = (selection as? SingleTargetSelector.State.Locked)?.target?.let { target ->
            detections.firstOrNull { it.code == target.code } ?: target
        }

    /** Whether [selected] was picked by a tap rather than by the app. */
    val selectedByTap: Boolean get() = selected?.code?.let { it == pinned } ?: false

    /** The fields captions show, given every collection's custom columns. */
    val captionFields: List<CaptionField>
        get() = captions.fieldsFor(customColumns.flatMap { it.customColumns }.distinct())
}

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

    @Volatile
    private var pendingSmoothing: CornerSmoother.Params? = null

    init {
        // A refreshed copy or a new schema can change any answer: look the labels up again.
        viewModelScope.launch {
            container.database.copy().observeState()
                .map { it?.refreshedAt to it?.schemaVersion }
                .distinctUntilChanged()
                .collect { (refreshedAt, _) ->
                    lookup.invalidate()
                    val schema = container.localCopy.schema()
                    _state.update { it.copy(plants = lookup.results, schema = schema, refreshedAt = refreshedAt) }
                }
        }
        viewModelScope.launch {
            container.captions.settings.collect { settings -> _state.update { it.copy(captions = settings) } }
        }
        viewModelScope.launch {
            container.localCopy.customColumns().collect { columns ->
                _state.update { it.copy(customColumns = columns) }
            }
        }
    }

    /** Saves new caption settings; the state follows once they are stored. */
    fun setCaptions(settings: CaptionSettings) {
        viewModelScope.launch { container.captions.save(settings) }
    }

    fun setResolution(resolution: AnalysisResolution) {
        if (resolution == _state.value.resolution) return
        resetRequested = true
        _state.update { it.copy(resolution = resolution) }
    }

    /** New 1€ filter settings for the overlay, applied from the next frame. */
    fun setSmoothing(params: CornerSmoother.Params) {
        pendingSmoothing = params
        _state.update { it.copy(smoothing = params) }
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
        pendingSmoothing?.let {
            pendingSmoothing = null
            smoother.params = it
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
