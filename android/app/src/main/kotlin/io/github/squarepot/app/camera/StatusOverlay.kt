// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import io.github.squarepot.app.R
import io.github.squarepot.app.data.STATUS_ORDER
import io.github.squarepot.app.data.StatusFailure
import io.github.squarepot.app.data.StatusOutcome
import io.github.squarepot.app.data.api.FieldSchemaDto
import io.github.squarepot.app.data.valueLabel

/** The status sheet of one plant from its card: the statuses, "lost" first, and clearing one it has. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun StatusSheet(
    tag: String,
    current: String?,
    schema: FieldSchemaDto?,
    editable: Boolean,
    busy: Boolean,
    onSet: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(stringResource(R.string.status_title, tag), style = MaterialTheme.typography.titleMedium)
            StatusChoices(schema, editable, busy, onSet)
            if (editable && !current.isNullOrEmpty()) {
                TextButton(onClick = { onSet("") }, enabled = !busy) { Text(stringResource(R.string.status_clear)) }
            }
        }
    }
}

/**
 * The statuses to set, the first ("lost") as the main button; for a collection read by link, why
 * none can be set instead.
 */
@Composable
internal fun StatusChoices(schema: FieldSchemaDto?, editable: Boolean, busy: Boolean, onSet: (String) -> Unit) {
    if (!editable) {
        Text(stringResource(R.string.status_read_only), style = MaterialTheme.typography.bodyMedium)
        return
    }
    val language = LocalConfiguration.current.locales[0].language
    Text(stringResource(R.string.status_hint), style = MaterialTheme.typography.bodySmall)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        STATUS_ORDER.forEachIndexed { i, key ->
            val label = schema.valueLabel(STATUS, key, language)
            if (i == 0) {
                Button(onClick = { onSet(key) }, enabled = !busy) { Text(label) }
            } else {
                OutlinedButton(onClick = { onSet(key) }, enabled = !busy) { Text(label) }
            }
        }
    }
}

/** What a status request did, in a sentence. */
@Composable
internal fun statusOutcomeText(outcome: StatusOutcome): String = when (outcome) {
    is StatusOutcome.Done -> stringResource(R.string.status_done, outcome.written, outcome.changed, outcome.missing)

    StatusOutcome.NotConfigured -> stringResource(R.string.status_not_configured)

    is StatusOutcome.Failed -> {
        val why = when (outcome.failure) {
            StatusFailure.NOT_EDITABLE -> stringResource(R.string.status_failed_read_only)
            StatusFailure.REJECTED -> stringResource(R.string.status_failed_rejected, outcome.message.orEmpty())
            StatusFailure.UNAUTHORIZED -> stringResource(R.string.failure_unauthorized)
            StatusFailure.NETWORK -> stringResource(R.string.failure_network)
            StatusFailure.SERVER -> stringResource(R.string.failure_server)
            StatusFailure.RATE_LIMITED -> stringResource(R.string.failure_rate_limited)
            StatusFailure.CLEARTEXT -> stringResource(R.string.failure_cleartext)
            StatusFailure.BAD_RESPONSE -> stringResource(R.string.failure_bad_response)
        }
        stringResource(R.string.status_failed, why)
    }
}

private const val STATUS = "status"
