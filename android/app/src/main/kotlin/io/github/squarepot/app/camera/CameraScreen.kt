// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.pm.PackageManager
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.view.CameraController
import androidx.camera.view.LifecycleCameraController
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.waitForUpOrCancellation
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.squarepot.app.BuildConfig
import io.github.squarepot.app.R
import io.github.squarepot.app.data.copyText
import io.github.squarepot.app.recognition.CornerSmoother
import io.github.squarepot.app.recognition.RollingStats
import io.github.squarepot.app.recognition.SingleTargetSelector
import io.github.squarepot.app.recognition.TagCode
import io.github.squarepot.app.recognition.isHit
import java.time.LocalDate
import java.util.Locale
import java.util.concurrent.Executors

@Composable
fun CameraScreen(viewModel: CameraViewModel, onOpenBench: () -> Unit, onOpenCopy: () -> Unit) {
    val context = LocalContext.current
    var granted by remember { mutableStateOf(context.hasCameraPermission()) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted = it }
    LaunchedEffect(Unit) {
        if (!granted) launcher.launch(Manifest.permission.CAMERA)
    }

    val density = LocalDensity.current
    var controlsHeight by remember { mutableStateOf(0.dp) }
    Box(Modifier.fillMaxSize().background(Color.Black)) {
        if (granted) {
            LiveCamera(viewModel, reservedBottom = controlsHeight)
        } else {
            Text(
                stringResource(R.string.camera_permission_needed),
                color = Color.White,
                modifier = Modifier.align(Alignment.Center).padding(24.dp),
            )
        }
        Controls(
            viewModel,
            onOpenBench,
            onOpenCopy,
            Modifier
                .align(Alignment.BottomCenter)
                .onSizeChanged { controlsHeight = with(density) { it.height.toDp() } },
        )
    }
}

@Composable
private fun LiveCamera(viewModel: CameraViewModel, reservedBottom: Dp) {
    val context = LocalContext.current
    val texts = rememberCaptionTexts()
    val lifecycleOwner = LocalLifecycleOwner.current
    val haptics = LocalHapticFeedback.current
    val state by viewModel.state.collectAsStateWithLifecycle()

    val controller = remember {
        LifecycleCameraController(context).apply {
            setEnabledUseCases(CameraController.IMAGE_ANALYSIS)
            previewResolutionSelector = ResolutionSelector.Builder()
                .setAspectRatioStrategy(AspectRatioStrategy.RATIO_16_9_FALLBACK_AUTO_STRATEGY)
                .build()
            imageAnalysisResolutionSelector = state.resolution.selector()
            imageAnalysisBackpressureStrategy = ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST
        }
    }
    var appliedResolution by remember { mutableStateOf(state.resolution) }
    // The analysis thread lives exactly as long as the binding to this lifecycle owner.
    DisposableEffect(lifecycleOwner, controller) {
        val executor = Executors.newSingleThreadExecutor()
        controller.setImageAnalysisAnalyzer(executor, TagAnalyzer(viewModel.decoder, viewModel::onFrame))
        controller.bindToLifecycle(lifecycleOwner)
        onDispose {
            controller.unbind()
            controller.clearImageAnalysisAnalyzer()
            executor.shutdown()
        }
    }

    // Changing the selector makes the controller rebind the camera.
    LaunchedEffect(controller, state.resolution) {
        if (state.resolution != appliedResolution) {
            controller.imageAnalysisResolutionSelector = state.resolution.selector()
            appliedResolution = state.resolution
        }
    }

    // Haptic tick when a label locks.
    val lockedCode = (state.selection as? SingleTargetSelector.State.Locked)?.target?.code
    LaunchedEffect(lockedCode) {
        if (lockedCode != null) haptics.performHapticFeedback(HapticFeedbackType.LongPress)
    }

    Box(Modifier.fillMaxSize().pickOnTap(viewModel, context, texts)) {
        AndroidView(
            factory = { ctx ->
                PreviewView(ctx).apply {
                    scaleType = PreviewView.ScaleType.FILL_CENTER
                    this.controller = controller
                }
            },
            modifier = Modifier.fillMaxSize(),
        )
        TagOverlay(
            state,
            Modifier.fillMaxSize(),
            reservedTop = WindowInsets.safeDrawing.asPaddingValues().calculateTopPadding(),
            reservedBottom = reservedBottom,
        )
    }
}

/**
 * A tap on a label picks it as the target; a tap on the label picked that way copies its caption;
 * a tap where there is no label goes back to choosing automatically.
 */
private fun Modifier.pickOnTap(viewModel: CameraViewModel, context: Context, texts: CaptionTexts) =
    pointerInput(viewModel, texts) {
        // PreviewView consumes every touch (tap to focus, pinch to zoom), so a tap detector in the
        // usual pass never fires. Watch taps in the Initial pass, before the preview, and leave them
        // unconsumed so the preview still focuses where the label was tapped.
        awaitEachGesture {
            val down = awaitFirstDown(requireUnconsumed = false, pass = PointerEventPass.Initial)
            val up = waitForUpOrCancellation(PointerEventPass.Initial) ?: return@awaitEachGesture
            val quick = up.uptimeMillis - down.uptimeMillis < viewConfiguration.longPressTimeoutMillis
            val still = (up.position - down.position).getDistance() < viewConfiguration.touchSlop
            if (!quick || !still) return@awaitEachGesture

            val current = viewModel.state.value
            val frame = current.frame ?: return@awaitEachGesture
            val map = FrameToView(frame, size.width.toFloat(), size.height.toFloat())
            val tap = SingleTargetSelector.Tap(map.toFrame(up.position), TAP_REACH.toPx() / map.scale)
            val selected = current.selected
            if (selected != null && current.selectedByTap && selected.isHit(tap)) {
                val content = current.captionContent(selected.code, texts, LocalDate.now())
                context.copyCaption(content, selected.code, texts)
            }
            viewModel.tap(tap)
        }
    }

/** Hidden sliders for the overlay's 1€ filter, so the best values can be found on the phone. */
@Composable
private fun SmoothingTuner(params: CornerSmoother.Params, onChange: (CornerSmoother.Params) -> Unit) {
    val style = MaterialTheme.typography.bodySmall
    Text(String.format(Locale.ROOT, "1€ min cutoff %.2f Hz", params.minCutoff), color = Color.White, style = style)
    Slider(
        value = params.minCutoff,
        onValueChange = { onChange(params.copy(minCutoff = it)) },
        valueRange = 0.05f..5f,
    )
    Text(String.format(Locale.ROOT, "1€ beta %.3f", params.beta), color = Color.White, style = style)
    Slider(
        value = params.beta,
        onValueChange = { onChange(params.copy(beta = it)) },
        valueRange = 0f..0.5f,
    )
}

@Composable
private fun Controls(
    viewModel: CameraViewModel,
    onOpenBench: () -> Unit,
    onOpenCopy: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    Column(
        modifier
            .fillMaxWidth()
            .background(Color.Black.copy(alpha = 0.55f))
            .safeDrawingPadding()
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        // Which build this is, so a phone run can be matched to its commit at a glance. A long
        // press opens the hidden overlay tuning.
        var tuning by rememberSaveable { mutableStateOf(false) }
        Text(
            BUILD,
            color = Color.White,
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.pointerInput(Unit) { detectTapGestures(onLongPress = { tuning = !tuning }) },
        )
        if (tuning) SmoothingTuner(state.smoothing, viewModel::setSmoothing)
        state.frame?.let {
            Text("${it.width}×${it.height}", color = Color.White, style = MaterialTheme.typography.bodySmall)
        }
        state.stats.toSortedMap().forEach { (id, s) ->
            if (s.frames > 0) Text(formatStats(id, s), color = Color.White, style = MaterialTheme.typography.bodySmall)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            AnalysisResolution.entries.forEach { r ->
                FilterChip(
                    selected = state.resolution == r,
                    onClick = { viewModel.setResolution(r) },
                    label = { Text(stringResource(r.label), color = Color.White) },
                )
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = onOpenBench) { Text(stringResource(R.string.open_bench)) }
            Button(onClick = onOpenCopy) { Text(stringResource(R.string.open_copy)) }
        }
    }
}

private fun formatStats(id: String, s: RollingStats.Snapshot): String = String.format(
    Locale.ROOT,
    "%s: %.0f%% frames, %.1f ms median, %.1f ms p95 (n=%d)",
    id,
    s.hitRate * PERCENT,
    s.medianMillis,
    s.p95Millis,
    s.frames,
)

private fun Context.hasCameraPermission() =
    ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

/** Copies a caption as one line; without plant data to copy, the label number as before. */
private fun Context.copyCaption(content: CaptionContent, code: TagCode, texts: CaptionTexts) {
    val lines = (content as? CaptionContent.Lines)?.lines.orEmpty()
    val (text, message) = if (lines.isEmpty()) {
        code.value to getString(R.string.copied, code.value)
    } else {
        lines.copyText(texts::age) to getString(R.string.caption_copied)
    }
    getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText(text, text))
    Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
}

private val AnalysisResolution.label: Int
    get() = when (this) {
        AnalysisResolution.P720 -> R.string.resolution_720
        AnalysisResolution.P1080 -> R.string.resolution_1080
        AnalysisResolution.MAX -> R.string.resolution_max
    }

private const val PERCENT = 100f

/** How far from a label a tap still picks it. */
private val TAP_REACH = 32.dp

private val BUILD = "${BuildConfig.VERSION_NAME} · ${BuildConfig.COMMIT.take(SHORT_COMMIT)}"
private const val SHORT_COMMIT = 7
