package io.github.squarepot.app.camera

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.squarepot.app.recognition.Detection
import io.github.squarepot.app.recognition.FrameSize
import io.github.squarepot.app.recognition.SingleTargetSelector.State
import kotlin.math.max

/**
 * Draws the crosshair, every detected label (thin), and the selected one (yellow while tracking,
 * green when locked, with its number).
 *
 * Assumes the preview fills the view with centre crop (PreviewView FILL_CENTER) and shows the
 * same field of view as the analysis frame: both use a 16:9 resolution.
 */
@Composable
fun TagOverlay(state: CameraUiState, modifier: Modifier = Modifier) {
    val textMeasurer = rememberTextMeasurer()
    Canvas(modifier) {
        drawCrosshair()
        val frame = state.frame ?: return@Canvas
        val map = FrameToView(frame, size.width, size.height)

        state.detections.forEach { drawQuad(it, map, Color.White.copy(alpha = 0.6f), 1.dp.toPx()) }

        val (target, color) = when (val s = state.selection) {
            is State.Locked -> s.target to LOCKED
            is State.Tracking -> s.target to TRACKING
            State.Searching -> return@Canvas
        }
        drawQuad(target, map, color, 3.dp.toPx())
        val top = target.corners.minBy { it.y }
        val anchor = map(top.x, top.y)
        val label = textMeasurer.measure(
            target.code.value,
            TextStyle(color = color, fontSize = 22.sp, fontWeight = FontWeight.Bold),
        )
        drawText(
            label,
            topLeft = Offset(anchor.x - label.size.width / 2f, anchor.y - label.size.height - 8.dp.toPx()),
        )
    }
}

/** Maps upright frame pixels to view pixels for a centre-cropped preview. */
private class FrameToView(frame: FrameSize, viewWidth: Float, viewHeight: Float) {
    private val scale = max(viewWidth / frame.width, viewHeight / frame.height)
    private val dx = (viewWidth - frame.width * scale) / 2
    private val dy = (viewHeight - frame.height * scale) / 2

    operator fun invoke(x: Float, y: Float) = Offset(x * scale + dx, y * scale + dy)
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

private fun DrawScope.drawCrosshair() {
    val arm = 16.dp.toPx()
    val c = center
    val color = Color.White.copy(alpha = 0.8f)
    drawLine(color, Offset(c.x - arm, c.y), Offset(c.x + arm, c.y), 2.dp.toPx())
    drawLine(color, Offset(c.x, c.y - arm), Offset(c.x, c.y + arm), 2.dp.toPx())
}

private val LOCKED = Color(0xFF4CAF50)
private val TRACKING = Color(0xFFFFC107)
