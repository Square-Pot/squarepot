// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import io.github.squarepot.app.data.PlantView
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger

/**
 * Looks decoded label numbers up in the local copy: each number once, in [scope], never on the
 * analysis thread. [onResult] is called after each lookup completes, so the caller can publish
 * [results]. An empty list means the copy has no plant with that number; more than one means
 * several plants share it.
 */
class TagLookup(
    private val scope: CoroutineScope,
    private val lookup: suspend (String) -> List<PlantView>,
    private val onResult: () -> Unit,
) {
    private val found = ConcurrentHashMap<String, List<PlantView>>()
    private val requested = ConcurrentHashMap.newKeySet<String>()

    /** Bumped by [invalidate], so a lookup started before it does not store a stale answer. */
    private val generation = AtomicInteger()

    /** What is known so far, by label number. Numbers still being looked up are absent. */
    val results: Map<String, List<PlantView>> get() = HashMap(found)

    /** Starts a lookup for each number not yet known or under way. */
    fun request(numbers: Collection<String>) {
        numbers.forEach { number ->
            if (!requested.add(number)) return@forEach
            val started = generation.get()
            scope.launch {
                val plants = lookup(number)
                if (generation.get() == started) {
                    found[number] = plants
                    onResult()
                }
            }
        }
    }

    /** Forgets every answer, for example after the copy was refreshed; numbers are looked up again on request. */
    fun invalidate() {
        generation.incrementAndGet()
        requested.clear()
        found.clear()
    }
}
