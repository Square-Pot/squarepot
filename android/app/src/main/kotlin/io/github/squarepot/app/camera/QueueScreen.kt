// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import android.text.format.DateUtils
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.squarepot.app.R
import io.github.squarepot.app.data.api.SightingKind
import io.github.squarepot.app.data.queue.QueueItem
import io.github.squarepot.app.data.queue.QueueProblem

/**
 * What waits to be sent (opened from the queue chip on the camera). Items the server refused say
 * why, and the owner retries or discards them; the rest go out as soon as the phone is online.
 */
@Composable
fun QueueScreen(viewModel: InventoryViewModel, onBack: () -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding()) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(4.dp)) {
            IconButton(onClick = onBack) {
                Icon(painterResource(R.drawable.ic_back), contentDescription = stringResource(R.string.back))
            }
            Text(stringResource(R.string.queue_title), style = MaterialTheme.typography.titleLarge)
        }
        val hint = if (state.queue.isEmpty()) R.string.queue_empty else R.string.queue_hint
        Text(
            stringResource(hint),
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
        LazyColumn(
            Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(state.queue, key = { it.key }) { item ->
                QueueRow(item, onRetry = { viewModel.retry(item) }, onDiscard = { viewModel.discard(item) })
            }
        }
    }
}

@Composable
private fun QueueRow(item: QueueItem, onRetry: () -> Unit, onDiscard: () -> Unit) {
    val context = LocalContext.current
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant).padding(12.dp)) {
        val what = when (item) {
            is QueueItem.Photo -> stringResource(R.string.queue_photo, item.tag)

            is QueueItem.Sighting -> if (item.sighting.kind == SightingKind.STATUS) {
                stringResource(R.string.queue_status, item.tag)
            } else {
                stringResource(R.string.queue_seen, item.tag)
            }
        }
        val at = DateUtils.formatDateTime(context, item.at, DateUtils.FORMAT_SHOW_DATE or DateUtils.FORMAT_SHOW_TIME)
        Text("$what · $at", style = MaterialTheme.typography.bodyMedium)
        (item as? QueueItem.Photo)?.photo?.comment?.let { Text("«$it»", style = MaterialTheme.typography.bodySmall) }
        item.problem?.let { problem ->
            Text(
                stringResource(problem.text),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = onRetry) { Text(stringResource(R.string.queue_retry)) }
                TextButton(onClick = onDiscard) { Text(stringResource(R.string.queue_discard)) }
            }
        }
    }
}

private val QueueItem.key: String
    get() = when (this) {
        is QueueItem.Photo -> "photo:" + photo.id
        is QueueItem.Sighting -> "sighting:" + sighting.id
    }

private val QueueProblem.text: Int
    get() = when (this) {
        QueueProblem.UNKNOWN_NUMBER -> R.string.problem_unknown_number
        QueueProblem.TOO_LARGE -> R.string.problem_too_large
        QueueProblem.REJECTED -> R.string.problem_rejected
        QueueProblem.MISSING_FILE -> R.string.problem_missing_file
    }
