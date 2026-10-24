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
import androidx.compose.foundation.gestures.waitForUpOrCancellation
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.squarepot.app.BuildConfig
import io.github.squarepot.app.R
import io.github.squarepot.app.data.PlantView
import io.github.squarepot.app.recognition.RollingStats
import io.github.squarepot.app.recognition.SingleTargetSelector
import io.github.squarepot.app.recognition.isHit
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

    Box(Modifier.fillMaxSize().background(Color.Black)) {
        if (granted) {
            LiveCamera(viewModel)
        } else {
            Text(
                stringResource(R.string.camera_permission_needed),
                color = Color.White,
                modifier = Modifier.align(Alignment.Center).padding(24.dp),
            )
        }
        Controls(viewModel, onOpenBench, onOpenCopy, Modifier.align(Alignment.BottomCenter))
    }
}

@Composable
private fun LiveCamera(viewModel: CameraViewModel) {
    val context = LocalContext.current
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

    Box(Modifier.fillMaxSize().pickOnTap(viewModel, context)) {
        AndroidView(
            factory = { ctx ->
                PreviewView(ctx).apply {
                    scaleType = PreviewView.ScaleType.FILL_CENTER
                    this.controller = controller
                }
            },
            modifier = Modifier.fillMaxSize(),
        )
        TagOverlay(state, Modifier.fillMaxSize())
    }
}

/**
 * A tap on a label picks it as the target; a tap on the locked one also copies its number; a tap
 * where there is no label goes back to choosing automatically.
 */
private fun Modifier.pickOnTap(viewModel: CameraViewModel, context: Context) = pointerInput(viewModel) {
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
        val locked = (current.selection as? SingleTargetSelector.State.Locked)?.target
        if (locked != null && locked.isHit(tap)) context.copyToClipboard(locked.code.value)
        viewModel.tap(tap)
    }
}

/**
 * The selected label's plant from the local copy: its name, or why there is none. A plain line in
 * the panel until the caption layout is settled.
 */
@Composable
private fun TargetPlant(state: CameraUiState) {
    val target = when (val s = state.selection) {
        is SingleTargetSelector.State.Locked -> s.target
        is SingleTargetSelector.State.Tracking -> s.target
        SingleTargetSelector.State.Searching -> null
    } ?: return
    val plants = state.plants[target.code.value] ?: return
    val text = when (plants.size) {
        0 -> AnnotatedString(stringResource(R.string.lookup_none))
        1 -> plants.single().caption()
        else -> AnnotatedString(stringResource(R.string.lookup_collision))
    }
    Text(text, color = Color.White, style = MaterialTheme.typography.titleMedium)
}

/** The plant's botanical name with its italics, or its first field when it has no name. */
private fun PlantView.caption(): AnnotatedString = buildAnnotatedString {
    if (name.isEmpty()) append(fields.firstOrNull { it.key != TAG_FIELD }?.value ?: tag.orEmpty())
    name.forEach { run ->
        if (run.italic) withStyle(SpanStyle(fontStyle = FontStyle.Italic)) { append(run.text) } else append(run.text)
    }
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
        TargetPlant(state)
        // Which build this is, so a phone run can be matched to its commit at a glance.
        Text(BUILD, color = Color.White, style = MaterialTheme.typography.bodySmall)
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

private fun Context.copyToClipboard(text: String) {
    getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText(text, text))
    Toast.makeText(this, getString(R.string.copied, text), Toast.LENGTH_SHORT).show()
}

private val AnalysisResolution.label: Int
    get() = when (this) {
        AnalysisResolution.P720 -> R.string.resolution_720
        AnalysisResolution.P1080 -> R.string.resolution_1080
        AnalysisResolution.MAX -> R.string.resolution_max
    }

private const val PERCENT = 100f

private const val TAG_FIELD = "tag"

/** How far from a label a tap still picks it. */
private val TAP_REACH = 32.dp

private val BUILD = "${BuildConfig.VERSION_NAME} · ${BuildConfig.COMMIT.take(SHORT_COMMIT)}"
private const val SHORT_COMMIT = 7
