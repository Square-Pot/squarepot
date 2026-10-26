// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.copy

import android.text.format.DateUtils
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import io.github.squarepot.app.R
import io.github.squarepot.app.data.PlantView
import io.github.squarepot.app.data.ServerSettings
import io.github.squarepot.app.data.SettingsProblem
import io.github.squarepot.app.data.SyncFailure
import io.github.squarepot.app.data.local.CollectionEntity

/** The local copy: how fresh it is, a lookup by label number, its collections and the server settings. */
@Composable
fun CopyScreen(viewModel: CopyViewModel = viewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val check by viewModel.check.collectAsStateWithLifecycle()
    val lookup by viewModel.lookup.collectAsStateWithLifecycle()
    val configured = state.settings.isComplete
    val server: @Composable () -> Unit = {
        ServerCard(state.settings, check, viewModel::saveSettings, viewModel::checkSettings, viewModel::clearCheck)
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().safeDrawingPadding(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { Text(stringResource(R.string.copy_title), style = MaterialTheme.typography.headlineSmall) }
        if (!configured) {
            item { server() }
        }
        item { StatusCard(state, configured, viewModel::refresh) }
        item { LookupCard(lookup, viewModel::setQuery, viewModel::search) }
        if (state.collections.isNotEmpty()) {
            item { Text(stringResource(R.string.collections_title), style = MaterialTheme.typography.titleMedium) }
            items(state.collections, key = { it.id }) { CollectionRow(it) }
        }
        if (configured) {
            item { server() }
        }
    }
}

@Composable
private fun StatusCard(state: CopyState, configured: Boolean, onRefresh: () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            val refreshed = state.refreshedAt
            Text(
                if (refreshed == null) {
                    stringResource(R.string.copy_never)
                } else {
                    stringResource(R.string.copy_refreshed, formatTime(refreshed))
                },
                style = MaterialTheme.typography.titleMedium,
            )
            if (refreshed != null) {
                Text(pluralStringResource(R.plurals.copy_plants, state.plantCount, state.plantCount))
            }
            when (state.activity) {
                SyncActivity.RUNNING -> Text(stringResource(R.string.sync_running))
                SyncActivity.QUEUED -> Text(stringResource(R.string.sync_queued))
                SyncActivity.IDLE -> state.failure?.let {
                    Text(
                        stringResource(R.string.sync_failed, failureText(it)),
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
            if (configured) {
                Button(onClick = onRefresh, enabled = state.activity != SyncActivity.RUNNING) {
                    Text(stringResource(R.string.copy_refresh))
                }
            } else {
                Text(stringResource(R.string.server_missing))
            }
        }
    }
}

@Composable
private fun LookupCard(lookup: LookupState, onQuery: (String) -> Unit, onSearch: () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stringResource(R.string.lookup_title), style = MaterialTheme.typography.titleMedium)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = lookup.query,
                    onValueChange = { input -> onQuery(input.filter(Char::isDigit).take(TAG_DIGITS)) },
                    label = { Text(stringResource(R.string.lookup_hint)) },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Number,
                        imeAction = ImeAction.Search,
                    ),
                    keyboardActions = KeyboardActions(onSearch = { onSearch() }),
                    modifier = Modifier.weight(1f),
                )
                Button(onClick = onSearch, enabled = lookup.query.isNotEmpty()) {
                    Text(stringResource(R.string.lookup_search))
                }
            }
            if (lookup.searched && lookup.plants.isEmpty()) Text(stringResource(R.string.lookup_none))
            if (lookup.plants.size > 1) {
                Text(stringResource(R.string.lookup_collision), color = MaterialTheme.colorScheme.error)
            }
            lookup.plants.forEach { PlantDetails(it) }
        }
    }
}

@Composable
private fun PlantDetails(plant: PlantView) {
    Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(
            listOfNotNull(plant.tag, plant.collectionName).joinToString(" · "),
            style = MaterialTheme.typography.titleSmall,
        )
        plant.fields.forEach { field ->
            Text("${field.label}: ${field.value}", style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun CollectionRow(collection: CollectionEntity) {
    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(collection.name, style = MaterialTheme.typography.bodyLarge)
        Text(
            pluralStringResource(R.plurals.copy_plants, collection.plantCount, collection.plantCount),
            style = MaterialTheme.typography.bodySmall,
        )
        val serverSynced = collection.serverSyncedAt
        Text(
            if (serverSynced == null) {
                stringResource(R.string.collection_server_never)
            } else {
                stringResource(R.string.collection_server_synced, formatTime(serverSynced))
            },
            style = MaterialTheme.typography.bodySmall,
        )
        collection.serverError?.let {
            Text(
                stringResource(R.string.collection_server_error, it),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
        }
    }
}

@Composable
private fun ServerCard(
    settings: ServerSettings,
    check: CheckResult?,
    onSave: (ServerSettings) -> Unit,
    onCheck: (ServerSettings) -> Unit,
    onEdit: () -> Unit,
) {
    var url by rememberSaveable(settings.url) { mutableStateOf(settings.url) }
    var token by rememberSaveable(settings.token) { mutableStateOf(settings.token) }
    val edited = ServerSettings(url, token)

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stringResource(R.string.server_title), style = MaterialTheme.typography.titleMedium)
            OutlinedTextField(
                value = url,
                onValueChange = {
                    url = it
                    onEdit()
                },
                label = { Text(stringResource(R.string.server_url)) },
                placeholder = { Text(stringResource(R.string.server_url_hint)) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = token,
                onValueChange = {
                    token = it
                    onEdit()
                },
                label = { Text(stringResource(R.string.server_token)) },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                modifier = Modifier.fillMaxWidth(),
            )
            check?.let { Text(checkText(it)) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { onCheck(edited) }, enabled = check != CheckResult.Running) {
                    Text(stringResource(R.string.server_check))
                }
                Button(onClick = { onSave(edited) }, enabled = edited.isComplete && edited != settings) {
                    Text(stringResource(R.string.server_save))
                }
            }
        }
    }
}

@Composable
private fun checkText(check: CheckResult): String = when (check) {
    CheckResult.Running -> stringResource(R.string.check_running)
    is CheckResult.Invalid -> stringResource(
        when (check.problem) {
            SettingsProblem.URL -> R.string.check_bad_url
            SettingsProblem.TOKEN -> R.string.check_bad_token
        },
    )
    is CheckResult.Reachable -> pluralStringResource(R.plurals.check_ok, check.collections, check.collections)
    is CheckResult.Failed -> failureText(check.failure)
}

@Composable
private fun failureText(failure: SyncFailure): String = stringResource(
    when (failure) {
        SyncFailure.UNAUTHORIZED -> R.string.failure_unauthorized
        SyncFailure.NETWORK -> R.string.failure_network
        SyncFailure.SERVER -> R.string.failure_server
        SyncFailure.RATE_LIMITED -> R.string.failure_rate_limited
        SyncFailure.BAD_RESPONSE -> R.string.failure_bad_response
        SyncFailure.CLEARTEXT -> R.string.failure_cleartext
    },
)

@Composable
private fun formatTime(millis: Long): String = DateUtils.formatDateTime(
    LocalContext.current,
    millis,
    DateUtils.FORMAT_SHOW_DATE or DateUtils.FORMAT_SHOW_TIME or DateUtils.FORMAT_ABBREV_MONTH,
)

private const val TAG_DIGITS = 6
