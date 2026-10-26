// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import android.text.format.DateUtils
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.selection.selectable
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.SheetValue
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.squarepot.app.R
import io.github.squarepot.app.data.PlantView
import io.github.squarepot.app.data.valueLabel
import io.github.squarepot.app.recognition.TagCode
import java.time.LocalDate

/**
 * The walk at the bottom of the camera in inventory mode: how many plants of the walk were seen
 * since it began (a tap opens the walk), and what waits to be sent (a tap opens the queue).
 */
@Composable
internal fun WalkBar(
    inventory: InventoryUiState,
    onOpenWalk: () -> Unit,
    onOpenQueue: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    Row(
        modifier
            .fillMaxWidth()
            .windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Bottom + WindowInsetsSides.Horizontal))
            .padding(horizontal = 12.dp, vertical = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        val since = DateUtils.formatDateTime(context, inventory.walk.startedAt, DateUtils.FORMAT_SHOW_DATE)
        val progress = inventory.progress
        Text(
            stringResource(R.string.walk_progress, progress.seen, progress.total, since),
            color = Color.White,
            fontSize = 12.5.sp,
            modifier = Modifier
                .weight(1f)
                .background(WALK_SCRIM)
                .clickable(onClick = onOpenWalk)
                .padding(horizontal = 10.dp, vertical = 8.dp),
        )
        if (inventory.waiting > 0) {
            val text = if (inventory.problems > 0) {
                stringResource(R.string.queue_chip_problems, inventory.waiting, inventory.problems)
            } else {
                stringResource(R.string.queue_chip, inventory.waiting)
            }
            Text(
                text,
                color = Color.White,
                fontSize = 12.5.sp,
                modifier = Modifier
                    .background(if (inventory.problems > 0) PROBLEM else WALK_SCRIM)
                    .clickable(onClick = onOpenQueue)
                    .padding(horizontal = 10.dp, vertical = 8.dp),
            )
        }
    }
}

/**
 * The card a tap on a label opens in inventory mode: the plant's caption, when it was last seen,
 * its photos and status, "Take photo", "Seen, no photo" and "Status…". Only these record a
 * sighting: the scan that opened the card does not.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun PlantCardSheet(
    tag: TagCode,
    camera: CameraUiState,
    inventory: InventoryUiState,
    onSeen: (TagCode) -> Unit,
    onTakePhoto: () -> Unit,
    onStatus: () -> Unit,
    onDismiss: () -> Unit,
) {
    val texts = rememberCaptionTexts()
    val seen = tag.value in inventory.seen
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                if (seen) "✓ ${tag.value}" else tag.value,
                style = MaterialTheme.typography.titleMedium.copy(fontFamily = FontFamily.Monospace),
            )
            when (val content = camera.captionContent(tag, texts, LocalDate.now())) {
                CaptionContent.Pending -> Unit

                CaptionContent.Collision -> {
                    Text(texts.collision, style = MaterialTheme.typography.bodyLarge)
                    Text(stringResource(R.string.card_collision_hint), style = MaterialTheme.typography.bodySmall)
                }

                is CaptionContent.NotInCopy -> {
                    Text(texts.notInCopy, style = MaterialTheme.typography.bodyLarge)
                    Text(content.hint, style = MaterialTheme.typography.bodySmall)
                }

                is CaptionContent.Lines -> {
                    val muted = MaterialTheme.colorScheme.onSurfaceVariant
                    content.lines.forEach { Text(it.annotated(muted, texts::age)) }
                    camera.plants[tag.value]?.singleOrNull()?.let { plant ->
                        PlantFacts(plant, camera, seen)
                        Button(onClick = onTakePhoto, modifier = Modifier.fillMaxWidth()) {
                            Text(stringResource(R.string.card_take_photo))
                        }
                        OutlinedButton(onClick = { onSeen(tag) }, modifier = Modifier.fillMaxWidth()) {
                            Text(stringResource(R.string.card_seen_no_photo))
                        }
                        TextButton(onClick = onStatus) { Text(stringResource(R.string.card_status_button)) }
                    }
                }
            }
        }
    }
}

/**
 * The photo just taken: what it shows, whose it is when it shows two plants of the copy (the
 * others can be marked as seen), an optional comment, and "Save" or "Retake". It cannot be swiped
 * away, so a photo is never lost by accident.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun PhotoReviewSheet(review: PhotoReview, camera: CameraUiState, photos: PhotoViewModel) {
    val sheet = rememberModalBottomSheetState(
        skipPartiallyExpanded = true,
        confirmValueChange = { it != SheetValue.Hidden },
    )
    ModalBottomSheet(onDismissRequest = {}, sheetState = sheet) {
        Column(
            Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                stringResource(R.string.review_title, review.owner),
                style = MaterialTheme.typography.titleMedium.copy(fontFamily = FontFamily.Monospace),
            )
            review.preview?.let {
                Image(
                    it,
                    contentDescription = null,
                    modifier = Modifier.fillMaxWidth().heightIn(max = 260.dp),
                    contentScale = ContentScale.Fit,
                )
            }
            if (review.labels == null) {
                Text(stringResource(R.string.review_reading), style = MaterialTheme.typography.bodySmall)
            }
            if (review.askWhose) Whose(review, camera, photos)
            OutlinedTextField(
                review.comment,
                onValueChange = photos::setComment,
                label = { Text(stringResource(R.string.review_comment)) },
                maxLines = 3,
                modifier = Modifier.fillMaxWidth(),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = photos::discard) { Text(stringResource(R.string.review_retake)) }
                Button(onClick = photos::save, enabled = review.labels != null, modifier = Modifier.weight(1f)) {
                    Text(stringResource(R.string.review_save))
                }
            }
        }
    }
}

/** "Whose photo is this?": one of the plants on it, and whether to mark the others as seen. */
@Composable
private fun Whose(review: PhotoReview, camera: CameraUiState, photos: PhotoViewModel) {
    Text(stringResource(R.string.review_whose), style = MaterialTheme.typography.titleSmall)
    review.labels.orEmpty().forEach { tag ->
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .fillMaxWidth()
                .selectable(tag == review.owner, onClick = { photos.setOwner(tag) }, role = Role.RadioButton),
        ) {
            RadioButton(selected = tag == review.owner, onClick = null)
            val name = camera.plants[tag]?.singleOrNull()?.name?.annotated()
            Text(
                buildAnnotatedString {
                    append(tag)
                    if (name != null) {
                        append("  ")
                        append(name)
                    }
                },
                modifier = Modifier.padding(start = 8.dp),
            )
        }
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Checkbox(checked = review.alsoSeen, onCheckedChange = photos::setAlsoSeen)
        Text(stringResource(R.string.review_also_seen, review.others.joinToString()))
    }
}

/** When the plant was last seen, how many photos it has, and its status if it has one. */
@Composable
private fun PlantFacts(plant: PlantView, camera: CameraUiState, seenInWalk: Boolean) {
    val context = LocalContext.current
    val style = MaterialTheme.typography.bodyMedium
    val lastSeen = when {
        seenInWalk -> stringResource(R.string.card_seen_in_walk)

        plant.lastSeen == null -> stringResource(R.string.card_never_seen)

        else -> {
            val at = DateUtils.formatDateTime(context, plant.lastSeen, DATE_AND_TIME)
            stringResource(R.string.card_last_seen, at)
        }
    }
    Text(lastSeen, style = style)
    Text(pluralStringResource(R.plurals.card_photos, plant.photoCount, plant.photoCount), style = style)
    plant.fields.firstOrNull { it.key == STATUS }?.let {
        val language = LocalConfiguration.current.locales[0].language
        Text(stringResource(R.string.card_status, camera.schema.valueLabel(STATUS, it.value, language)), style = style)
    }
}

private const val STATUS = "status"
private const val DATE_AND_TIME = DateUtils.FORMAT_SHOW_DATE or DateUtils.FORMAT_SHOW_TIME
private val WALK_SCRIM = Color(0xFF0A0C0A).copy(alpha = 0.62f)
private val PROBLEM = Color(0xFFB3261E)
