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
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.squarepot.app.R
import io.github.squarepot.app.data.api.FieldSchemaDto
import io.github.squarepot.app.data.botanicalName
import io.github.squarepot.app.data.local.PlantEntity

/**
 * The plants of the walk nobody saw since it began (opened from the walk). The owner picks the
 * ones that are gone and gives them a status at once, "lost" first (ADR 0008); a collection read
 * by link cannot be written, and says so.
 */
@Composable
fun NotSeenScreen(
    camera: CameraViewModel,
    inventory: InventoryViewModel,
    status: StatusViewModel,
    onBack: () -> Unit,
) {
    val schema = camera.state.collectAsStateWithLifecycle().value.schema
    val walk by inventory.state.collectAsStateWithLifecycle()
    val edit by status.state.collectAsStateWithLifecycle()
    val notSeen = walk.notSeen
    val editable = walk.collections.filter { it.editable }.mapTo(HashSet()) { it.id }
    val selectable = notSeen.filter { it.collectionId in editable }
    // The outcome shows here; leaving the screen drops it, so the camera does not show it again.
    DisposableEffect(status) { onDispose { status.outcomeShown() } }
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding()) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(4.dp)) {
            IconButton(onClick = onBack) {
                Icon(painterResource(R.drawable.ic_back), contentDescription = stringResource(R.string.back))
            }
            Text(stringResource(R.string.not_seen_title), style = MaterialTheme.typography.titleLarge)
            if (selectable.isNotEmpty()) {
                TextButton(onClick = { status.select(selectable.mapTo(HashSet()) { it.id }) }) {
                    Text(stringResource(R.string.not_seen_select_all))
                }
            }
        }
        Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            edit.outcome?.let { Text(statusOutcomeText(it), style = MaterialTheme.typography.bodyMedium) }
            if (notSeen.isEmpty()) Text(stringResource(R.string.not_seen_empty))
            val picked = selectable.filter { it.id in edit.selected }
            if (picked.isNotEmpty() || selectable.size < notSeen.size) {
                val count = stringResource(R.string.not_seen_selected, picked.size)
                Text(count, style = MaterialTheme.typography.bodySmall)
                StatusChoices(schema, editable = selectable.isNotEmpty(), busy = edit.busy) {
                    status.apply(picked, it, fromCard = false)
                }
            }
        }
        LazyColumn(
            Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            items(notSeen, key = { it.id }) { plant ->
                NotSeenRow(plant, schema, plant.collectionId in editable, plant.id in edit.selected) {
                    status.toggle(plant.id)
                }
            }
        }
    }
}

@Composable
private fun NotSeenRow(
    plant: PlantEntity,
    schema: FieldSchemaDto?,
    editable: Boolean,
    selected: Boolean,
    onToggle: () -> Unit,
) {
    val context = LocalContext.current
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .toggleable(selected, enabled = editable, role = Role.Checkbox, onValueChange = { onToggle() }),
    ) {
        Checkbox(checked = selected, onCheckedChange = null, enabled = editable)
        Column(Modifier.padding(start = 8.dp)) {
            Text(plant.tag.orEmpty(), fontFamily = FontFamily.Monospace)
            Text(botanicalName(schema, plant.fields).annotated(), style = MaterialTheme.typography.bodyMedium)
            val seen = plant.lastSeen?.let { DateUtils.formatDateTime(context, it, DateUtils.FORMAT_SHOW_DATE) }
            Text(
                seen?.let { stringResource(R.string.card_last_seen, it) } ?: stringResource(R.string.card_never_seen),
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}
