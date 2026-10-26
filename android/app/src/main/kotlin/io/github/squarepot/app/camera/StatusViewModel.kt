// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import io.github.squarepot.app.SquarepotApplication
import io.github.squarepot.app.data.StatusOutcome
import io.github.squarepot.app.data.api.SightingKind
import io.github.squarepot.app.data.local.PlantEntity
import io.github.squarepot.app.data.written
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class StatusUiState(
    /** Plant ids picked on the "not seen" list. */
    val selected: Set<String> = emptySet(),
    /** A request is on its way. */
    val busy: Boolean = false,
    /** The last request's outcome, to show once. */
    val outcome: StatusOutcome? = null,
)

/**
 * Status from the apps (ADR 0006, 0008): for many plants a walk did not find, or for one from its
 * card. It needs the server, so nothing is queued; from a card, a written status is also a sighting.
 */
class StatusViewModel(application: Application) : AndroidViewModel(application) {
    private val container = (application as SquarepotApplication).container
    private val _state = MutableStateFlow(StatusUiState())
    val state: StateFlow<StatusUiState> = _state.asStateFlow()

    fun toggle(id: String) = _state.update {
        it.copy(selected = if (id in it.selected) it.selected - id else it.selected + id)
    }

    fun select(ids: Set<String>) = _state.update { it.copy(selected = ids) }

    /** Sets [status] (empty clears it) for [plants]; [fromCard] also records that they were seen. */
    fun apply(plants: List<PlantEntity>, status: String, fromCard: Boolean) {
        if (plants.isEmpty() || _state.value.busy) return
        _state.update { it.copy(busy = true) }
        viewModelScope.launch {
            val outcome = container.setStatus(plants, status)
            if (fromCard && outcome.written > 0) {
                plants.mapNotNull { it.tag }.forEach { container.outbox.seen(it, SightingKind.STATUS) }
            }
            _state.update {
                it.copy(
                    busy = false,
                    outcome = outcome,
                    selected = if (outcome is StatusOutcome.Done) emptySet() else it.selected,
                )
            }
        }
    }

    fun outcomeShown() = _state.update { it.copy(outcome = null) }
}
