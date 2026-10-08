package io.github.squarepot.app.bench

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.squarepot.app.R
import java.util.Locale

@Composable
fun BenchScreen(viewModel: BenchViewModel, onBack: () -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val pickFolder = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        if (uri != null) viewModel.run(uri)
    }

    Column(
        Modifier
            .fillMaxSize()
            .safeDrawingPadding()
            .padding(16.dp)
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(stringResource(R.string.bench_title), style = MaterialTheme.typography.headlineSmall)
        Text(stringResource(R.string.bench_explanation))

        when (val s = state) {
            BenchUiState.Idle -> Unit

            is BenchUiState.Running -> {
                Text(stringResource(R.string.bench_progress, s.done, s.total))
                LinearProgressIndicator(
                    progress = { if (s.total == 0) 0f else s.done.toFloat() / s.total },
                    modifier = Modifier.fillMaxWidth(),
                )
            }

            is BenchUiState.Done -> {
                Text(stringResource(R.string.bench_saved, s.result.outputName))
                Text(formatSummary(s.result), style = MaterialTheme.typography.bodySmall)
            }

            is BenchUiState.Failed -> Text(stringResource(R.string.bench_failed, s.message))
        }

        Button(onClick = { pickFolder.launch(null) }, enabled = state !is BenchUiState.Running) {
            Text(stringResource(R.string.bench_pick_folder))
        }
        OutlinedButton(onClick = onBack) { Text(stringResource(R.string.back)) }
    }
}

private fun formatSummary(result: BenchRunner.Result): String = buildString {
    appendLine("photos: ${result.photos}, labelled in ${BenchManifest.FILE_NAME}: ${result.labelledPhotos}")
    result.summary.decoders.forEach {
        appendLine(
            String.format(
                Locale.ROOT,
                "%s: %d/%d photos decoded, %d codes, %.1f ms median, %.1f ms p95",
                it.decoderId,
                it.photosDecoded,
                it.photos,
                it.codes,
                it.medianMillis,
                it.p95Millis,
            ),
        )
        if (it.labelled.photos > 0) {
            appendLine("  labelled: ${formatScore(it.labelled)}")
            it.byCondition.forEach { (condition, score) -> appendLine("  $condition: ${formatScore(score)}") }
        }
    }
    result.summary.onlyDecodedBy.forEach { (id, n) -> appendLine("only $id: $n") }
    append("decoded by none: ${result.summary.decodedByNone}")
}

private fun formatScore(s: Score): String = String.format(
    Locale.ROOT,
    "%d/%d correct (%.0f%%), %d wrong",
    s.correct,
    s.expected,
    s.rate * PERCENT,
    s.wrong,
)

private const val PERCENT = 100f
