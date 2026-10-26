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
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
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
import io.github.squarepot.app.data.CaptionPlace
import io.github.squarepot.app.data.copyText
import io.github.squarepot.app.recognition.SingleTargetSelector
import io.github.squarepot.app.recognition.TagCode
import io.github.squarepot.app.recognition.isHit
import java.time.LocalDate
import java.util.concurrent.Executors

/**
 * The live camera with the controls over it: the copy's status, inventory mode, ⚙ for the caption
 * settings and the torch at the top; the label count, or panel B when captions go there, at the
 * bottom; and the hidden 1€ panel when it is open. In inventory mode the walk takes the bottom,
 * and a tap on a label opens the plant's card.
 */
@Composable
fun CameraScreen(
    viewModel: CameraViewModel,
    inventory: InventoryViewModel,
    onOpenSettings: () -> Unit,
    onOpenCopy: () -> Unit,
    onOpenWalk: () -> Unit,
    onOpenQueue: () -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val inventoryState by inventory.state.collectAsStateWithLifecycle()
    val inventoryOn = inventoryState.walk.active
    val density = LocalDensity.current
    var topHeight by remember { mutableStateOf(0.dp) }
    var bottomHeight by remember { mutableStateOf(0.dp) }
    Box(Modifier.fillMaxSize().background(Color.Black)) {
        CameraOrPermission {
            LiveCamera(
                viewModel,
                cards = inventory.takeIf { inventoryOn },
                seen = if (inventoryOn) inventoryState.seen else emptySet(),
                reservedTop = topHeight,
                reservedBottom = bottomHeight,
            )
        }
        CameraTopBar(
            state,
            inventory = inventoryOn,
            onOpenCopy = onOpenCopy,
            onInventory = { inventory.setActive(!inventoryOn) },
            onOpenSettings = onOpenSettings,
            onTorch = { viewModel.setTorch(!state.torch) },
            modifier = Modifier
                .align(Alignment.TopCenter)
                .onSizeChanged { topHeight = with(density) { it.height.toDp() } },
        )
        CameraBottom(
            viewModel,
            inventoryState.takeIf { inventoryOn },
            onOpenWalk = onOpenWalk,
            onOpenQueue = onOpenQueue,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .onSizeChanged { bottomHeight = with(density) { it.height.toDp() } },
        )
        if (state.tuning) {
            TuningPanel(
                state,
                onChange = viewModel::setSmoothing,
                onClose = { viewModel.setTuning(false) },
                modifier = Modifier.align(Alignment.TopStart).padding(start = 12.dp, top = topHeight),
            )
        }
        inventoryState.card?.takeIf { inventoryOn }?.let { tag ->
            PlantCardSheet(tag, state, inventoryState, onSeen = inventory::markSeen, onDismiss = inventory::closeCard)
        }
    }
}

/** Asks for the camera once; shows [camera] when it is granted, else why the app needs it. */
@Composable
private fun BoxScope.CameraOrPermission(camera: @Composable () -> Unit) {
    val context = LocalContext.current
    var granted by remember { mutableStateOf(context.hasCameraPermission()) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted = it }
    LaunchedEffect(Unit) {
        if (!granted) launcher.launch(Manifest.permission.CAMERA)
    }
    if (granted) {
        camera()
    } else {
        Text(
            stringResource(R.string.camera_permission_needed),
            color = Color.White,
            modifier = Modifier.align(Alignment.Center).padding(24.dp),
        )
    }
}

/** The bottom of the camera: the walk in inventory mode ([walk] not null), else panel B or the label count. */
@Composable
private fun CameraBottom(
    viewModel: CameraViewModel,
    walk: InventoryUiState?,
    onOpenWalk: () -> Unit,
    onOpenQueue: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    when {
        walk != null -> WalkBar(walk, onOpenWalk = onOpenWalk, onOpenQueue = onOpenQueue, modifier = modifier)

        state.captions.place == CaptionPlace.PANEL -> CaptionPanel(
            state,
            onFold = { viewModel.setCaptions(state.captions.copy(panelFolded = !state.captions.panelFolded)) },
            onToggleTuning = { viewModel.setTuning(!state.tuning) },
            modifier = modifier,
        )

        else -> LabelCount(state, modifier)
    }
}

/** The preview and its overlay; [cards] opens a plant's card on a tap in inventory mode, else null. */
@Composable
private fun LiveCamera(
    viewModel: CameraViewModel,
    cards: InventoryViewModel?,
    seen: Set<String>,
    reservedTop: Dp,
    reservedBottom: Dp,
) {
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

    LaunchedEffect(controller, state.torch) { controller.enableTorch(state.torch) }

    // Haptic tick when a label locks.
    val lockedCode = (state.selection as? SingleTargetSelector.State.Locked)?.target?.code
    LaunchedEffect(lockedCode) {
        if (lockedCode != null) haptics.performHapticFeedback(HapticFeedbackType.LongPress)
    }

    Box(Modifier.fillMaxSize().pickOnTap(viewModel, cards, context, texts)) {
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
            reservedTop = reservedTop,
            reservedBottom = reservedBottom,
            seen = seen,
        )
    }
}

/**
 * A tap on a label picks it as the target; a tap on the label picked that way copies its caption;
 * a tap where there is no label goes back to choosing automatically. In inventory mode ([cards]
 * not null), a tap on any label picks it and opens its card instead of copying.
 */
private fun Modifier.pickOnTap(
    viewModel: CameraViewModel,
    cards: InventoryViewModel?,
    context: Context,
    texts: CaptionTexts,
) = pointerInput(viewModel, cards, texts) {
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
        if (cards != null) {
            current.detections.firstOrNull { it.isHit(tap) }?.let { cards.openCard(it.code) }
        } else if (selected != null && current.selectedByTap && selected.isHit(tap)) {
            val content = current.captionContent(selected.code, texts, LocalDate.now())
            context.copyCaption(content, selected.code, texts)
        }
        viewModel.tap(tap)
    }
}

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

internal val AnalysisResolution.label: Int
    get() = when (this) {
        AnalysisResolution.P720 -> R.string.resolution_720
        AnalysisResolution.P1080 -> R.string.resolution_1080
        AnalysisResolution.MAX -> R.string.resolution_max
    }

/** How far from a label a tap still picks it. */
private val TAP_REACH = 32.dp

/** Which build this is, so a phone run can be matched to its commit at a glance. */
internal val BUILD = "${BuildConfig.VERSION_NAME} · ${BuildConfig.COMMIT.take(SHORT_COMMIT)}"
private const val SHORT_COMMIT = 7
