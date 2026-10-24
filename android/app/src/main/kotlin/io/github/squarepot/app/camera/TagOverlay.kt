// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.squarepot.app.recognition.Detection
import io.github.squarepot.app.recognition.FrameSize
import io.github.squarepot.app.recognition.Point
import io.github.squarepot.app.recognition.SingleTargetSelector
import io.github.squarepot.app.recognition.SingleTargetSelector.State
import kotlin.math.max

/**
 * Draws the aim mark, every decoded label (thin, with its number in small type) and the selected
 * one (yellow while tracking, green when locked, with its number in large type).
 *
 * Assumes the preview fills the view with centre crop (PreviewView FILL_CENTER) and shows the
 * same field of view as the analysis frame: both use a 16:9 resolution.
 */
@Composable
fun TagOverlay(state: CameraUiState, modifier: Modifier = Modifier) {
    val textMeasurer = rememberTextMeasurer()
    Canvas(modifier) {
        val frame = state.frame ?: return@Canvas
        val map = FrameToView(frame, size.width, size.height)
        drawAimMark(map(SingleTargetSelector.aimPoint(frame)))

        val (target, color) = when (val s = state.selection) {
            is State.Locked -> s.target to LOCKED
            is State.Tracking -> s.target to TRACKING
            State.Searching -> null to OTHER
        }

        state.detections.forEach {
            drawQuad(it, map, OTHER, 1.dp.toPx())
            if (it.code != target?.code) {
                drawCode(it, map, textMeasurer.measure(it.code.value, TextStyle(color = OTHER, fontSize = 13.sp)))
            }
        }

        if (target == null) return@Canvas
        drawQuad(target, map, color, 3.dp.toPx())
        val label = textMeasurer.measure(
            target.code.value,
            TextStyle(color = color, fontSize = 22.sp, fontWeight = FontWeight.Bold),
        )
        drawCode(target, map, label)
    }
}

/** Writes a label's number centred above its top corner. */
private fun DrawScope.drawCode(detection: Detection, map: FrameToView, label: TextLayoutResult) {
    val top = detection.corners.minBy { it.y }
    val anchor = map(top.x, top.y)
    drawText(
        label,
        topLeft = Offset(anchor.x - label.size.width / 2f, anchor.y - label.size.height - 8.dp.toPx()),
    )
}

/** A small cross where the selector aims, so the collector knows what "nearest the centre" means. */
private fun DrawScope.drawAimMark(at: Offset) {
    val arm = 10.dp.toPx()
    val width = 2.dp.toPx()
    drawLine(OTHER, Offset(at.x - arm, at.y), Offset(at.x + arm, at.y), width)
    drawLine(OTHER, Offset(at.x, at.y - arm), Offset(at.x, at.y + arm), width)
}

/** Maps upright frame pixels to view pixels for a centre-cropped preview, and back. */
internal class FrameToView(frame: FrameSize, viewWidth: Float, viewHeight: Float) {
    /** View pixels per frame pixel. */
    val scale = max(viewWidth / frame.width, viewHeight / frame.height)
    private val dx = (viewWidth - frame.width * scale) / 2
    private val dy = (viewHeight - frame.height * scale) / 2

    operator fun invoke(x: Float, y: Float) = Offset(x * scale + dx, y * scale + dy)

    operator fun invoke(p: Point) = invoke(p.x, p.y)

    fun toFrame(view: Offset) = Point((view.x - dx) / scale, (view.y - dy) / scale)
}

private fun DrawScope.drawQuad(detection: Detection, map: FrameToView, color: Color, width: Float) {
    val path = Path()
    detection.corners.forEachIndexed { i, p ->
        val o = map(p.x, p.y)
        if (i == 0) path.moveTo(o.x, o.y) else path.lineTo(o.x, o.y)
    }
    path.close()
    drawPath(path, color, style = Stroke(width))
}

private val OTHER = Color.White.copy(alpha = 0.6f)
private val LOCKED = Color(0xFF4CAF50)
private val TRACKING = Color(0xFFFFC107)
