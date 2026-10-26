// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import android.content.ClipData
import android.content.ClipboardManager
import android.text.format.DateUtils
import android.widget.Toast
import androidx.annotation.DrawableRes
import androidx.annotation.StringRes
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.squarepot.app.R
import io.github.squarepot.app.data.CaptionLine
import io.github.squarepot.app.recognition.CornerSmoother
import io.github.squarepot.app.recognition.RollingStats
import java.time.LocalDate
import java.util.Locale

/**
 * The status of the local copy, inventory mode, ⚙ for the caption settings and the torch, over
 * the top of the picture.
 */
@Composable
internal fun CameraTopBar(
    state: CameraUiState,
    inventory: Boolean,
    onOpenCopy: () -> Unit,
    onInventory: () -> Unit,
    onOpenSettings: () -> Unit,
    onTorch: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier
            .fillMaxWidth()
            .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal))
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        CopyChip(state.refreshedAt, onOpenCopy)
        Spacer(Modifier.weight(1f))
        ChromeButton(R.drawable.ic_inventory, R.string.inventory_mode, active = inventory, onClick = onInventory)
        ChromeButton(R.drawable.ic_settings, R.string.captions_open, active = false, onClick = onOpenSettings)
        ChromeButton(R.drawable.ic_torch, R.string.torch, active = state.torch, onClick = onTorch)
    }
}

/** When the copy was refreshed; a tap opens the local copy. */
@Composable
private fun CopyChip(refreshedAt: Long?, onClick: () -> Unit) {
    val context = LocalContext.current
    Row(
        Modifier.background(SURFACE).clickable(onClick = onClick).padding(horizontal = 10.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(7.dp),
    ) {
        Box(Modifier.size(7.dp).background(if (refreshedAt == null) Color.Gray else PICKED, CircleShape))
        val text = refreshedAt?.let {
            stringResource(R.string.copy_chip, DateUtils.formatDateTime(context, it, DateUtils.FORMAT_SHOW_TIME))
        } ?: stringResource(R.string.copy_chip_none)
        Text(text, color = ON_SURFACE, fontSize = 12.sp)
    }
}

@Composable
private fun ChromeButton(@DrawableRes icon: Int, @StringRes label: Int, active: Boolean, onClick: () -> Unit) {
    IconButton(
        onClick = onClick,
        colors = IconButtonDefaults.iconButtonColors(
            containerColor = if (active) PICKED else SURFACE,
            contentColor = ON_SURFACE,
        ),
    ) {
        Icon(painterResource(icon), contentDescription = stringResource(label), modifier = Modifier.size(20.dp))
    }
}

/** How many labels are in view, at the bottom when captions are at the labels. */
@Composable
internal fun LabelCount(state: CameraUiState, modifier: Modifier = Modifier) {
    Box(
        modifier
            .fillMaxWidth()
            .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Bottom))
            .padding(bottom = 22.dp),
        contentAlignment = Alignment.Center,
    ) {
        val count = state.detections.size
        val text = if (count == 0) {
            stringResource(R.string.point_at_label)
        } else {
            pluralStringResource(R.plurals.labels_in_view, count, count)
        }
        Text(
            text,
            color = Color.White,
            fontSize = 11.5.sp,
            modifier = Modifier.background(SCRIM).padding(horizontal = 10.dp, vertical = 4.dp),
        )
    }
}

/**
 * Panel B: the selected label's caption in a dark panel at the bottom. A tap on the handle folds
 * it to the name alone, and the panel remembers that. A long press on the version line opens the
 * hidden 1€ panel.
 */
@Composable
internal fun CaptionPanel(
    state: CameraUiState,
    onFold: () -> Unit,
    onToggleTuning: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val texts = rememberCaptionTexts()
    val folded = state.captions.panelFolded
    Column(
        modifier
            .fillMaxWidth()
            .background(PANEL)
            .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Bottom + WindowInsetsSides.Horizontal))
            .padding(start = 16.dp, end = 16.dp, bottom = 16.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(
            Modifier
                .align(Alignment.CenterHorizontally)
                .clickable(onClick = onFold)
                .padding(horizontal = 24.dp, vertical = 10.dp),
        ) {
            Box(Modifier.size(34.dp, 4.dp).background(HANDLE, RoundedCornerShape(2.dp)))
        }
        val selected = state.selected
        if (selected == null) {
            Text(stringResource(R.string.point_at_label), color = Color.White.copy(alpha = 0.7f), fontSize = 13.sp)
        } else {
            val color = if (state.selectedByTap) TAPPED else PICKED
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    selected.code.value,
                    style = PANEL_NUMBER.copy(color = onColor(color)),
                    modifier = Modifier.background(color).padding(horizontal = 6.dp, vertical = 2.dp),
                )
                Text(
                    if (state.selectedByTap) texts.yourPickCopy else texts.appPick,
                    color = Color.White.copy(alpha = 0.75f),
                    fontSize = 11.5.sp,
                )
            }
            PanelCaption(state.captionContent(selected.code, texts, LocalDate.now()), folded, texts)
        }
        Text(
            BUILD,
            style = PANEL_NUMBER.copy(color = Color.White.copy(alpha = 0.45f), fontSize = 10.sp),
            modifier = Modifier.pointerInput(Unit) { detectTapGestures(onLongPress = { onToggleTuning() }) },
        )
    }
}

/** The caption's lines in the panel; folded, the name alone on one line. */
@Composable
private fun PanelCaption(content: CaptionContent, folded: Boolean, texts: CaptionTexts) {
    val muted = Color.White.copy(alpha = 0.7f)
    when (content) {
        CaptionContent.Pending -> Unit

        CaptionContent.Collision -> Text(texts.collision, style = PANEL_NAME)

        is CaptionContent.NotInCopy -> {
            Text(texts.notInCopy, style = PANEL_NAME)
            if (!folded) Text(content.hint, style = PANEL_LINE)
        }

        is CaptionContent.Lines -> {
            val lines = if (folded) content.lines.filterIsInstance<CaptionLine.Name>() else content.lines
            lines.forEach { PanelLine(it, folded, muted, texts) }
        }
    }
}

@Composable
private fun PanelLine(line: CaptionLine, folded: Boolean, muted: Color, texts: CaptionTexts) {
    val style = when (line) {
        is CaptionLine.FieldNumber -> PANEL_NUMBER.copy(color = muted)
        is CaptionLine.Name -> if (folded) PANEL_NAME.copy(fontSize = 16.sp) else PANEL_NAME
        else -> PANEL_LINE
    }
    val maxLines = if (folded) 1 else (line as? CaptionLine.Name)?.maxLines ?: Int.MAX_VALUE
    Text(line.annotated(muted, texts::age), style = style, maxLines = maxLines, overflow = TextOverflow.Ellipsis)
}

/**
 * The hidden panel for the overlay's 1€ filter, opened by a long press on the version line: its
 * two settings (applied from the next frame), a reset, the values to copy for a report, and the
 * decoder's live figures.
 */
@Composable
internal fun TuningPanel(
    state: CameraUiState,
    onChange: (CornerSmoother.Params) -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val params = state.smoothing
    val values = String.format(Locale.ROOT, "minCutoff=%.2f beta=%.3f", params.minCutoff, params.beta)
    val copied = stringResource(R.string.copied, values)
    Column(modifier.width(240.dp).background(TUNING).padding(horizontal = 12.dp, vertical = 8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.tuning_title), style = TUNING_TEXT, modifier = Modifier.weight(1f))
            IconButton(onClick = onClose, modifier = Modifier.size(32.dp)) {
                Icon(
                    painterResource(R.drawable.ic_close),
                    contentDescription = stringResource(R.string.close),
                    tint = Color.White,
                    modifier = Modifier.size(16.dp),
                )
            }
        }
        Text(String.format(Locale.ROOT, "minCutoff %.2f Hz", params.minCutoff), style = TUNING_TEXT)
        Slider(
            value = params.minCutoff,
            onValueChange = { onChange(params.copy(minCutoff = it)) },
            valueRange = 0.05f..5f,
        )
        Text(String.format(Locale.ROOT, "beta %.3f", params.beta), style = TUNING_TEXT)
        Slider(value = params.beta, onValueChange = { onChange(params.copy(beta = it)) }, valueRange = 0f..0.5f)
        Row {
            TextButton(onClick = { onChange(CornerSmoother.Params()) }) { Text(stringResource(R.string.tuning_reset)) }
            TextButton(
                onClick = {
                    context.getSystemService(ClipboardManager::class.java)
                        .setPrimaryClip(ClipData.newPlainText(values, values))
                    Toast.makeText(context, copied, Toast.LENGTH_SHORT).show()
                },
            ) { Text(stringResource(R.string.tuning_copy)) }
        }
        state.frame?.let { Text("${it.width}×${it.height}", style = TUNING_TEXT) }
        state.stats.toSortedMap().forEach { (id, s) -> if (s.frames > 0) Text(formatStats(id, s), style = TUNING_TEXT) }
    }
}

private fun formatStats(id: String, s: RollingStats.Snapshot): String = String.format(
    Locale.ROOT,
    "%s: %.0f%% frames, %.1f ms median, %.1f ms p95 (n=%d)",
    id,
    s.hitRate * 100f,
    s.medianMillis,
    s.p95Millis,
    s.frames,
)

private val SURFACE = Color(0xFFF7F8F2)
private val ON_SURFACE = Color(0xFF1E2A22)
private val SCRIM = Color(0xFF0A0C0A).copy(alpha = 0.55f)
private val PANEL = Color(0xFF0C0F0D).copy(alpha = 0.80f)
private val HANDLE = Color.White.copy(alpha = 0.35f)
private val TUNING = Color(0xFF080A09).copy(alpha = 0.84f)

private val PANEL_NUMBER = TextStyle(
    fontFamily = FontFamily.Monospace,
    fontSize = 11.sp,
    fontWeight = FontWeight.Medium,
)
private val PANEL_NAME = TextStyle(
    color = Color(0xFFF2F4EE),
    fontFamily = FontFamily.Serif,
    fontSize = 19.sp,
    lineHeight = 22.sp,
)
private val PANEL_LINE = TextStyle(color = Color(0xFFF2F4EE), fontSize = 12.5.sp)
private val TUNING_TEXT = TextStyle(color = Color(0xFFE9EEE6), fontFamily = FontFamily.Monospace, fontSize = 11.sp)
