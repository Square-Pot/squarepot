// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.Shadow
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.squarepot.app.data.CaptionLine
import io.github.squarepot.app.data.CaptionLook
import io.github.squarepot.app.data.CaptionPlace
import io.github.squarepot.app.data.NeighbourNames
import io.github.squarepot.app.data.shortName
import io.github.squarepot.app.recognition.Detection
import io.github.squarepot.app.recognition.FrameSize
import io.github.squarepot.app.recognition.Point
import io.github.squarepot.app.recognition.SingleTargetSelector
import java.time.LocalDate
import kotlin.math.max

/**
 * Draws the aim mark, a frame on every decoded label with its number on a tab, and the selected
 * label in green (picked by the app) or blue (picked by a tap). With captions at the label, the
 * selected label's caption hangs off its number tab, right of the label or above it, never below
 * (see [CaptionPlacement]); neighbours keep their number and, if chosen, a short name.
 *
 * [reservedTop] and [reservedBottom] are kept free of captions, for the controls drawn over the
 * picture. Assumes the preview fills the view with centre crop (PreviewView FILL_CENTER) and
 * shows the same field of view as the analysis frame: both use a 16:9 resolution.
 */
@Composable
fun TagOverlay(
    state: CameraUiState,
    modifier: Modifier = Modifier,
    reservedTop: Dp = 0.dp,
    reservedBottom: Dp = 0.dp,
) {
    val measurer = rememberTextMeasurer()
    val texts = rememberCaptionTexts()
    val selected = state.selected
    val content = selected?.let { state.captionContent(it.code, texts, LocalDate.now()) }
    val atLabel = state.captions.place == CaptionPlace.LABEL
    Canvas(modifier) {
        val frame = state.frame ?: return@Canvas
        val map = FrameToView(frame, size.width, size.height)
        drawAimMark(map(SingleTargetSelector.aimPoint(frame)))
        val painter = OverlayPainter(this, measurer, map, texts)
        val color = if (state.selectedByTap) TAPPED else PICKED
        val neighbours = state.detections.filter { it.code != selected?.code }
        neighbours.forEach { painter.frame(it, PALE, 1.dp) }

        val taken = mutableListOf<ViewBox>()
        if (selected != null) {
            painter.frame(selected, color, 2.5.dp)
            val label = painter.bounds(selected)
            taken += if (atLabel && content != null) {
                val area = ViewBox(0f, reservedTop.toPx(), size.width, size.height - reservedBottom.toPx())
                val note = if (state.selectedByTap) texts.yourPick else null
                val card = CaptionCard(content, state.captions.look, color, note)
                painter.caption(card, selected.code.value, label, area)
            } else {
                painter.tab(selected.code.value, label, selectedTab(color))
            }
        }
        val withNames = atLabel && state.captions.neighbours == NeighbourNames.SHORT_NAME
        neighbours.sortedByDescending { it.area }.forEach { neighbour ->
            val plant = state.plants[neighbour.code.value]?.singleOrNull()
            val name = plant?.takeIf { withNames }?.let { shortName(it, state.schema) }.orEmpty()
            painter.neighbour(neighbour.code.value, painter.bounds(neighbour), name.annotated(), taken)
                ?.let { taken += it }
        }
    }
}

/** A caption to draw: what it says, its look and colour, and a note next to its number ("your pick"). */
private class CaptionCard(val content: CaptionContent, val look: CaptionLook, val color: Color, val note: String?)

private class TabStyle(val background: Color, val text: TextStyle)

private fun selectedTab(color: Color) =
    TabStyle(color, NUMBER.copy(color = onColor(color), fontWeight = FontWeight.Medium))

/** Draws one frame's overlay on [scope]; sizes are in dp, converted with the canvas's density. */
private class OverlayPainter(
    private val scope: DrawScope,
    private val measurer: TextMeasurer,
    private val map: FrameToView,
    private val texts: CaptionTexts,
) {
    private val tabHeight = with(scope) { TAB_HEIGHT.toPx() }

    fun frame(detection: Detection, color: Color, width: Dp) = with(scope) {
        val path = Path()
        detection.corners.forEachIndexed { i, p ->
            val o = map(p)
            if (i == 0) path.moveTo(o.x, o.y) else path.lineTo(o.x, o.y)
        }
        path.close()
        drawPath(path, color, style = Stroke(width.toPx()))
    }

    /** The label's frame as an axis-aligned box in view pixels. */
    fun bounds(detection: Detection): ViewBox {
        val points = detection.corners.map { map(it) }
        return ViewBox(points.minOf { it.x }, points.minOf { it.y }, points.maxOf { it.x }, points.maxOf { it.y })
    }

    /** A number tab on the label's top left corner; returns the box it covers. */
    fun tab(number: String, label: ViewBox, style: TabStyle): ViewBox {
        val text = measurer.measure(number, style.text)
        val box = ViewBox.of(label.left, label.top - tabHeight, tabWidth(text), tabHeight)
        drawTab(text, box.left, box.top, style.background)
        return box
    }

    /** A neighbour's tab with [name] when there is room, else its number alone, else nothing; returns its box. */
    fun neighbour(number: String, label: ViewBox, name: AnnotatedString, taken: List<ViewBox>): ViewBox? = with(scope) {
        val text = measurer.measure(number, NEIGHBOUR_TAB.text)
        val numberBox = ViewBox.of(label.left, label.top - tabHeight, tabWidth(text), tabHeight)
        val nameText = name.takeIf { it.isNotEmpty() }?.let {
            measurer.measure(
                it,
                NEIGHBOUR_NAME,
                overflow = TextOverflow.Ellipsis,
                maxLines = 1,
                constraints = widthAtMost(NAME_WIDTH),
            )
        }
        val nameBox = nameText?.let {
            ViewBox.of(numberBox.left, numberBox.top, numberBox.width + NAME_GAP.toPx() + it.size.width, tabHeight)
        }
        when (CaptionPlacement.neighbourTab(nameBox, numberBox, taken)) {
            NeighbourTab.HIDDEN -> null

            NeighbourTab.NUMBER -> numberBox.also { drawTab(text, it.left, it.top, NEIGHBOUR_TAB.background) }

            NeighbourTab.NUMBER_AND_NAME -> checkNotNull(nameBox).also {
                drawTab(text, it.left, it.top, NEIGHBOUR_TAB.background)
                val shown = checkNotNull(nameText)
                val top = it.top + (tabHeight - shown.size.height) / 2
                drawText(shown, topLeft = Offset(numberBox.right + NAME_GAP.toPx(), top))
            }
        }
    }

    /** The selected label's caption with its number tab; returns the box it covers. */
    fun caption(card: CaptionCard, number: String, label: ViewBox, area: ViewBox): ViewBox = with(scope) {
        val body = measureBody(card)
        val tab = measurer.measure(number, selectedTab(card.color).text)
        val note = card.note?.let { measurer.measure(it, NOTE) }
        val paper = card.look == CaptionLook.CARD
        val padX = if (paper) (CARD_PAD_START + CARD_PAD_END).toPx() else 0f
        val padY = if (paper) (CARD_PAD_TOP + CARD_PAD_BOTTOM).toPx() else BARE_PAD_TOP.toPx()
        val bodyWidth = (body.maxOfOrNull { it.size.width } ?: 0) + padX
        val bodyHeight = body.sumOf { it.size.height } + LINE_GAP.toPx() * max(0, body.size - 1) + padY
        val headWidth = tabWidth(tab) + (note?.let { NAME_GAP.toPx() + it.size.width } ?: 0f)
        val width = max(bodyWidth, headWidth)
        val height = if (body.isEmpty()) tabHeight else tabHeight + bodyHeight
        val spot = CaptionPlacement(tabHeight, CARD_GAP.toPx()).place(label, width, height, area)
        // On the right the tab is the card's top row, level with the label's top; above, its bottom row.
        val headTop = if (spot.side == CaptionSide.RIGHT) spot.box.top else spot.box.bottom - tabHeight
        val bodyTop = if (spot.side == CaptionSide.RIGHT) spot.box.top + tabHeight else spot.box.top
        if (body.isNotEmpty()) drawBody(card, body, ViewBox.of(spot.box.left, bodyTop, bodyWidth, bodyHeight))
        drawTab(tab, spot.box.left, headTop, card.color)
        note?.let {
            val left = spot.box.left + tabWidth(tab) + NAME_GAP.toPx()
            drawText(it, topLeft = Offset(left, headTop + (tabHeight - it.size.height) / 2))
        }
        spot.box
    }

    private fun measureBody(card: CaptionCard): List<TextLayoutResult> {
        val bare = card.look == CaptionLook.BARE
        val styles = if (bare) BARE_STYLES else CARD_STYLES
        val maxWidth = if (bare) BARE_WIDTH else CARD_WIDTH - CARD_PAD_START - CARD_PAD_END
        val lines: List<Pair<AnnotatedString, CaptionLine?>> = when (val c = card.content) {
            CaptionContent.Pending -> emptyList()

            CaptionContent.Collision -> listOf(AnnotatedString(texts.collision) to NAME_LINE)

            is CaptionContent.NotInCopy ->
                listOf(AnnotatedString(texts.notInCopy) to NAME_LINE, AnnotatedString(c.hint) to null)

            is CaptionContent.Lines -> c.lines.map { it.annotated(styles.muted, texts::age) to it }
        }
        return lines.map { (text, line) ->
            measurer.measure(
                text,
                styles.of(line),
                overflow = TextOverflow.Ellipsis,
                maxLines = (line as? CaptionLine.Name)?.maxLines ?: Int.MAX_VALUE,
                constraints = widthAtMost(maxWidth),
            )
        }
    }

    private fun drawBody(card: CaptionCard, lines: List<TextLayoutResult>, box: ViewBox) = with(scope) {
        val paper = card.look == CaptionLook.CARD
        if (paper) {
            drawRect(PAPER, Offset(box.left, box.top), Size(box.width, box.height))
            drawRect(PAPER_EDGE, Offset(box.left, box.top), Size(box.width, box.height), style = Stroke(1.dp.toPx()))
            drawRect(card.color, Offset(box.left, box.top), Size(ACCENT.toPx(), box.height))
        }
        var y = box.top + if (paper) CARD_PAD_TOP.toPx() else BARE_PAD_TOP.toPx()
        val x = box.left + if (paper) CARD_PAD_START.toPx() else 0f
        lines.forEach {
            drawText(it, topLeft = Offset(x, y))
            y += it.size.height + LINE_GAP.toPx()
        }
    }

    private fun drawTab(text: TextLayoutResult, left: Float, top: Float, background: Color) = with(scope) {
        drawRect(background, Offset(left, top), Size(tabWidth(text), tabHeight))
        drawText(text, topLeft = Offset(left + TAB_PAD.toPx(), top + (tabHeight - text.size.height) / 2))
    }

    private fun tabWidth(text: TextLayoutResult) = with(scope) { text.size.width + 2 * TAB_PAD.toPx() }

    private fun widthAtMost(width: Dp) = with(scope) { Constraints(maxWidth = width.roundToPx()) }
}

/** The styles of a caption's lines in one look; a null line is a plain one. */
private class LineStyles(val number: TextStyle, val name: TextStyle, val line: TextStyle, val muted: Color) {
    fun of(line: CaptionLine?): TextStyle = when (line) {
        is CaptionLine.FieldNumber -> number
        is CaptionLine.Name -> name
        else -> this.line
    }
}

/** Sets a line like a name, for the headings of "not in the copy" and "several plants". */
private val NAME_LINE = CaptionLine.Name(emptyList(), maxLines = null)

private val HALO = Shadow(Color.Black.copy(alpha = 0.95f), Offset(0f, 1f), blurRadius = 4f)

private val CARD_STYLES = LineStyles(
    number = TextStyle(color = Color(0xFF5E6B60), fontFamily = FontFamily.Monospace, fontSize = 10.5.sp),
    name = TextStyle(
        color = Color(0xFF1E2A22),
        fontFamily = FontFamily.Serif,
        fontSize = 15.5.sp,
        lineHeight = 17.5.sp,
    ),
    line = TextStyle(color = Color(0xFF1E2A22), fontSize = 11.5.sp, lineHeight = 15.sp),
    muted = Color(0xFF5E6B60),
)

private val BARE_STYLES = LineStyles(
    number = TextStyle(
        color = Color.White.copy(alpha = 0.85f),
        fontFamily = FontFamily.Monospace,
        fontSize = 10.5.sp,
        shadow = HALO,
    ),
    name = TextStyle(
        color = Color.White,
        fontFamily = FontFamily.Serif,
        fontWeight = FontWeight.Medium,
        fontSize = 16.sp,
        lineHeight = 18.sp,
        shadow = HALO,
    ),
    line = TextStyle(color = Color.White, fontSize = 11.5.sp, lineHeight = 15.sp, shadow = HALO),
    muted = Color.White.copy(alpha = 0.7f),
)

private val NUMBER = TextStyle(fontFamily = FontFamily.Monospace, fontSize = 10.5.sp)

// After NUMBER: top-level properties are initialised in the order they are written.
private val NEIGHBOUR_TAB = TabStyle(
    background = Color.Black.copy(alpha = 0.42f),
    text = NUMBER.copy(color = Color.White.copy(alpha = 0.82f)),
)
private val NOTE = TextStyle(color = Color.White, fontSize = 10.sp, shadow = HALO)
private val NEIGHBOUR_NAME = TextStyle(
    color = Color.White.copy(alpha = 0.78f),
    fontFamily = FontFamily.Serif,
    fontStyle = FontStyle.Italic,
    fontSize = 12.5.sp,
    shadow = HALO,
)

/** Text on a tab in [color]: dark blue on a tap's pick, dark green on the app's. */
private fun onColor(color: Color) = if (color == TAPPED) Color(0xFF06121F) else Color(0xFF0B1A10)

private val TAB_HEIGHT = 19.dp
private val TAB_PAD = 6.dp
private val NAME_GAP = 5.dp
private val NAME_WIDTH = 120.dp
private val CARD_WIDTH = 184.dp
private val BARE_WIDTH = 176.dp
private val CARD_GAP = 6.dp
private val CARD_PAD_START = 9.dp
private val CARD_PAD_END = 9.dp
private val CARD_PAD_TOP = 6.dp
private val CARD_PAD_BOTTOM = 7.dp
private val BARE_PAD_TOP = 2.dp
private val LINE_GAP = 3.dp
private val ACCENT = 3.dp

private val PAPER = Color(0xFFF7F8F2)
private val PAPER_EDGE = Color.Black.copy(alpha = 0.18f)

/** A cross where the selector aims, so the collector knows what "nearest the centre" means. */
private fun DrawScope.drawAimMark(at: Offset) {
    val arm = 10.dp.toPx()
    val width = 2.dp.toPx()
    drawLine(PALE, Offset(at.x - arm, at.y), Offset(at.x + arm, at.y), width)
    drawLine(PALE, Offset(at.x, at.y - arm), Offset(at.x, at.y + arm), width)
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

/** Colours on top of the video, the same in light and dark themes (mockup, 2026-10-24). */
internal val PICKED = Color(0xFF4CC37A)
internal val TAPPED = Color(0xFF4A9BFF)
internal val PALE = Color.White.copy(alpha = 0.55f)
