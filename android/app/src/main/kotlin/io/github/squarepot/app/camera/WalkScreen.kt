// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import android.text.format.DateUtils
import androidx.annotation.StringRes
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
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
import io.github.squarepot.app.data.columnValues
import io.github.squarepot.app.data.walkColumns

/**
 * The inventory walk (opened from the walk bar on the camera): inventory mode on or off, which
 * plants the walk covers (a collection, then optionally one value of one column, such as a
 * shelf), since when sightings count, and the plants not seen yet.
 */
@Composable
fun WalkScreen(viewModel: InventoryViewModel, onBack: () -> Unit, onOpenNotSeen: () -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val walk = state.walk
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding()) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(4.dp)) {
            IconButton(onClick = onBack) {
                Icon(painterResource(R.drawable.ic_back), contentDescription = stringResource(R.string.back))
            }
            Text(stringResource(R.string.walk_title), style = MaterialTheme.typography.titleLarge)
        }
        Column(
            Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(stringResource(R.string.walk_mode), style = MaterialTheme.typography.bodyLarge)
                    Text(stringResource(R.string.walk_mode_hint), style = MaterialTheme.typography.bodySmall)
                }
                Switch(checked = walk.active, onCheckedChange = viewModel::setActive)
            }
            Section(R.string.walk_collection)
            val collections = listOf(null to stringResource(R.string.walk_all_collections)) +
                state.collections.map { it.id to it.name }
            Chips(collections, walk.collectionId) { viewModel.setScope(it, null, null) }

            val custom = state.collections.firstOrNull { it.id == walk.collectionId }?.customColumns
                ?: state.collections.flatMap { it.customColumns }.distinct()
            val genus = stringResource(R.string.walk_genus)
            val columns = listOf(null to stringResource(R.string.walk_column_none)) +
                walkColumns(custom).map { it to if (it == GENUS) genus else it }
            Section(R.string.walk_column)
            Chips(columns, walk.column) { viewModel.setScope(walk.collectionId, it, null) }
            walk.column?.let { column ->
                val values = columnValues(state.plants, walk.collectionId, column)
                if (values.isEmpty()) {
                    Text(stringResource(R.string.walk_no_values), style = MaterialTheme.typography.bodySmall)
                } else {
                    Chips(values.map { it to it }, walk.value) { viewModel.setScope(walk.collectionId, column, it) }
                }
            }

            Section(R.string.walk_since_title)
            val since = DateUtils.formatDateTime(
                LocalContext.current,
                walk.startedAt,
                DateUtils.FORMAT_SHOW_DATE or DateUtils.FORMAT_SHOW_TIME,
            )
            Text(stringResource(R.string.walk_since, since), style = MaterialTheme.typography.bodyMedium)
            Text(
                stringResource(R.string.walk_in_scope, state.progress.total, state.progress.seen),
                style = MaterialTheme.typography.bodyMedium,
            )
            Button(onClick = onOpenNotSeen) { Text(stringResource(R.string.not_seen_open, state.notSeen.size)) }
            OutlinedButton(onClick = viewModel::restart) { Text(stringResource(R.string.walk_restart)) }
        }
    }
}

@Composable
private fun Section(@StringRes title: Int) {
    Text(stringResource(title), style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
}

@Composable
private fun <T> Chips(options: List<Pair<T, String>>, selected: T, onSelect: (T) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { (value, title) ->
            FilterChip(selected = value == selected, onClick = { onSelect(value) }, label = { Text(title) })
        }
    }
}

private const val GENUS = "genus"
