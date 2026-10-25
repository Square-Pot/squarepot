// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import androidx.annotation.StringRes
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.squarepot.app.R
import io.github.squarepot.app.data.CaptionField
import io.github.squarepot.app.data.CaptionLook
import io.github.squarepot.app.data.CaptionPlace
import io.github.squarepot.app.data.NameMode
import io.github.squarepot.app.data.NeighbourNames
import io.github.squarepot.app.data.PlantView
import io.github.squarepot.app.data.caption
import io.github.squarepot.app.data.copyText
import java.time.LocalDate

/**
 * How the camera captions labels (opened with ⚙ on the camera): where, how they look, which
 * fields in which order, long names and neighbours. The sample at the top is the copy's plant
 * with the longest name, so a choice that makes captions too long shows at once. The tools at
 * the bottom (analysis resolution, the photo bench, the version line that opens the hidden 1€
 * panel) are for measuring and tuning.
 */
@Composable
fun CaptionSettingsScreen(viewModel: CameraViewModel, onBack: () -> Unit, onOpenBench: () -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val sample by produceState<PlantView?>(null, state.refreshedAt) { value = viewModel.longestNamed() }
    val settings = state.captions
    val save = viewModel::setCaptions
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding()) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(4.dp)) {
            IconButton(onClick = onBack) {
                Icon(painterResource(R.drawable.ic_back), contentDescription = stringResource(R.string.back))
            }
            Text(stringResource(R.string.captions_title), style = MaterialTheme.typography.titleLarge)
        }
        Column(
            Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Sample(state, sample)
            Section(R.string.place_title)
            Option(R.string.place_label, R.string.place_label_hint, settings.place == CaptionPlace.LABEL) {
                save(settings.copy(place = CaptionPlace.LABEL))
            }
            Option(R.string.place_panel, R.string.place_panel_hint, settings.place == CaptionPlace.PANEL) {
                save(settings.copy(place = CaptionPlace.PANEL))
            }
            if (settings.place == CaptionPlace.LABEL) {
                Section(R.string.look_title)
                Choice(LOOKS, settings.look) { save(settings.copy(look = it)) }
            }
            Fields(state, sample) { save(settings.copy(fields = it)) }
            Section(R.string.names_title)
            Choice(NAME_MODES, settings.nameMode) { save(settings.copy(nameMode = it)) }
            Section(R.string.neighbours_title)
            Choice(NEIGHBOURS, settings.neighbours) { save(settings.copy(neighbours = it)) }
            if (settings.fields != null) {
                OutlinedButton(onClick = { save(settings.copy(fields = null)) }) {
                    Text(stringResource(R.string.fields_reset))
                }
            }
            Tools(state, viewModel, onOpenBench)
        }
    }
}

/** The sample caption, drawn as the camera would draw it, or why there is none. */
@Composable
private fun Sample(state: CameraUiState, sample: PlantView?) {
    val texts = rememberCaptionTexts()
    if (sample == null) {
        Text(stringResource(R.string.sample_none), style = MaterialTheme.typography.bodySmall)
        return
    }
    val lines = caption(sample, state.schema, state.captionFields, state.captions.nameMode, LocalDate.now())
    val number = sample.tag.orEmpty()
    if (state.captions.place == CaptionPlace.LABEL) {
        CaptionSample(
            CaptionContent.Lines(lines),
            state.captions.look,
            number,
            Modifier.fillMaxWidth().height(200.dp),
        )
    } else {
        Text(
            lines.copyText(texts::age),
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant).padding(12.dp),
        )
    }
}

/** The chosen fields in order, with a sample value each, and the fields and columns that can be added. */
@Composable
private fun Fields(state: CameraUiState, sample: PlantView?, onChange: (List<CaptionField>) -> Unit) {
    val chosen = state.captionFields
    val texts = rememberCaptionTexts()
    val catalogue = FieldCatalogue(state.schema, LocalConfiguration.current.locales[0].language)
    Section(R.string.fields_title)
    Text(stringResource(R.string.fields_note), style = MaterialTheme.typography.bodySmall)
    if (chosen.isEmpty()) Text(stringResource(R.string.fields_empty), style = MaterialTheme.typography.bodyMedium)
    chosen.forEachIndexed { i, field ->
        FieldRow(
            title = catalogue.titleOf(field),
            isColumn = field is CaptionField.Custom,
            example = sample?.let { state.sampleValue(it, field, texts, LocalDate.now()) },
            canMoveUp = i > 0,
            onMoveUp = { onChange(chosen.toMutableList().apply { add(i - 1, removeAt(i)) }) },
            onRemove = { onChange(chosen - field) },
        )
    }
    val schemaFields = catalogue.schema.filter { it.first !in chosen }
    if (schemaFields.isNotEmpty()) {
        Text(stringResource(R.string.fields_schema), style = MaterialTheme.typography.bodySmall)
        AddChips(schemaFields) { onChange(chosen + it) }
    }
    state.customColumns.forEach { collection ->
        val columns = collection.customColumns.map { CaptionField.Custom(it) }.filter { it !in chosen }
        if (columns.isEmpty()) return@forEach
        Text(stringResource(R.string.fields_custom, collection.name), style = MaterialTheme.typography.bodySmall)
        AddChips(columns.map { it to it.column }) { onChange(chosen + it) }
    }
}

@Composable
private fun FieldRow(
    title: String,
    isColumn: Boolean,
    example: String?,
    canMoveUp: Boolean,
    onMoveUp: () -> Unit,
    onRemove: () -> Unit,
) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant).padding(start = 12.dp),
    ) {
        Column(Modifier.weight(1f)) {
            val badge = if (isColumn) " · " + stringResource(R.string.fields_column_badge) else ""
            Text(title + badge, style = MaterialTheme.typography.titleSmall)
            Text(
                example?.takeIf { it.isNotEmpty() } ?: stringResource(R.string.fields_sample_empty),
                style = MaterialTheme.typography.bodySmall,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        IconButton(onClick = onMoveUp, enabled = canMoveUp) {
            Icon(painterResource(R.drawable.ic_arrow_up), contentDescription = stringResource(R.string.move_up))
        }
        IconButton(onClick = onRemove) {
            Icon(painterResource(R.drawable.ic_close), contentDescription = stringResource(R.string.remove))
        }
    }
}

@Composable
private fun AddChips(fields: List<Pair<CaptionField, String>>, onAdd: (CaptionField) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        fields.forEach { (field, title) ->
            FilterChip(selected = false, onClick = { onAdd(field) }, label = { Text("+ $title") })
        }
    }
}

/** Analysis resolution, the photo bench and the version line, whose long press opens the 1€ panel. */
@Composable
private fun Tools(state: CameraUiState, viewModel: CameraViewModel, onOpenBench: () -> Unit) {
    Section(R.string.tools_title)
    Text(stringResource(R.string.analysis_resolution), style = MaterialTheme.typography.bodySmall)
    Choice(AnalysisResolution.entries.map { it to it.label }, state.resolution, viewModel::setResolution)
    Button(onClick = onOpenBench) { Text(stringResource(R.string.open_bench)) }
    Text(
        BUILD,
        style = MaterialTheme.typography.bodySmall,
        modifier = Modifier.pointerInput(state.tuning) {
            detectTapGestures(onLongPress = { viewModel.setTuning(!state.tuning) })
        },
    )
    Text(stringResource(R.string.tuning_hint), style = MaterialTheme.typography.bodySmall)
}

@Composable
private fun Section(@StringRes title: Int) {
    Text(stringResource(title), style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
}

@Composable
private fun Option(@StringRes title: Int, @StringRes hint: Int, selected: Boolean, onSelect: () -> Unit) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.fillMaxWidth().selectable(selected, onClick = onSelect, role = Role.RadioButton),
    ) {
        RadioButton(selected = selected, onClick = null)
        Column(Modifier.padding(start = 8.dp)) {
            Text(stringResource(title), style = MaterialTheme.typography.bodyLarge)
            Text(stringResource(hint), style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun <T> Choice(options: List<Pair<T, Int>>, selected: T, onSelect: (T) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { (value, title) ->
            FilterChip(
                selected = value == selected,
                onClick = { onSelect(value) },
                label = { Text(stringResource(title)) },
            )
        }
    }
}

private val LOOKS = listOf(CaptionLook.CARD to R.string.look_card, CaptionLook.BARE to R.string.look_bare)
private val NAME_MODES = listOf(
    NameMode.FULL to R.string.names_full,
    NameMode.TWO_LINES to R.string.names_two_lines,
    NameMode.SHORT_GENUS to R.string.names_short_genus,
)
private val NEIGHBOURS = listOf(
    NeighbourNames.NUMBER_ONLY to R.string.neighbours_number,
    NeighbourNames.SHORT_NAME to R.string.neighbours_name,
)
