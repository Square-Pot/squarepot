// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import io.github.squarepot.app.SquarepotApplication
import io.github.squarepot.app.data.InventoryWalk
import io.github.squarepot.app.data.WalkProgress
import io.github.squarepot.app.data.api.SightingKind
import io.github.squarepot.app.data.local.CollectionEntity
import io.github.squarepot.app.data.local.PlantEntity
import io.github.squarepot.app.data.queue.QueueItem
import io.github.squarepot.app.recognition.TagCode
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class InventoryUiState(
    val walk: InventoryWalk = InventoryWalk(),
    val progress: WalkProgress = WalkProgress(seen = 0, total = 0),
    /** Numbers seen in this walk, for the ✓ on their tabs. */
    val seen: Set<String> = emptySet(),
    val collections: List<CollectionEntity> = emptyList(),
    val plants: List<PlantEntity> = emptyList(),
    /** What waits to be sent, oldest first. */
    val queue: List<QueueItem> = emptyList(),
    /** The label whose card is open on the camera. */
    val card: TagCode? = null,
) {
    val waiting: Int get() = queue.size
    val problems: Int get() = queue.count { it.problem != null }
}

/**
 * Inventory mode (ADR 0008, variant A): the walk, the card a tap opens, and the queue. A sighting
 * is recorded only by the owner's action on the card, never by a scan.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class InventoryViewModel(application: Application) : AndroidViewModel(application) {
    private val container = (application as SquarepotApplication).container
    private val card = MutableStateFlow<TagCode?>(null)

    private val walk = container.inventory.walk
    private val seenHere = walk.flatMapLatest { container.outbox.seenSince(it.startedAt) }

    val state: StateFlow<InventoryUiState> = combine(
        combine(walk, container.localCopy.plants(), seenHere, ::Triple),
        container.localCopy.collections(),
        container.outbox.items,
        card,
    ) { (current, plants, here), collections, queue, open ->
        InventoryUiState(
            walk = current,
            progress = current.progress(plants, here),
            seen = current.seenTags(plants, here),
            collections = collections,
            plants = plants,
            queue = queue,
            card = open,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(STOP_TIMEOUT_MILLIS), InventoryUiState())

    /** Turns inventory mode on or off; the first walk starts now. */
    fun setActive(on: Boolean) = save { current ->
        current.copy(active = on, startedAt = current.startedAt.takeIf { it > 0 } ?: now())
    }

    /** Narrows the walk to [collectionId] and, when [column] is given, to the plants with [value] in it. */
    fun setScope(collectionId: String?, column: String?, value: String?) = save {
        it.copy(collectionId = collectionId, column = column, value = value.takeIf { column != null })
    }

    /** Starts the walk over: only sightings from now on count. */
    fun restart() = save { it.copy(startedAt = now()) }

    fun openCard(tag: TagCode) {
        card.value = tag
    }

    fun closeCard() {
        card.value = null
    }

    /** "Seen, no photo" on the card: queues the sighting and closes the card. */
    fun markSeen(tag: TagCode) {
        viewModelScope.launch { container.outbox.seen(tag.value, SightingKind.SEEN) }
        closeCard()
    }

    fun retry(item: QueueItem) {
        viewModelScope.launch { container.outbox.retry(item) }
    }

    fun discard(item: QueueItem) {
        viewModelScope.launch { container.outbox.discard(item) }
    }

    private fun save(change: (InventoryWalk) -> InventoryWalk) {
        viewModelScope.launch { container.inventory.update(change) }
    }

    private fun now() = System.currentTimeMillis()

    private companion object {
        const val STOP_TIMEOUT_MILLIS = 5_000L
    }
}
