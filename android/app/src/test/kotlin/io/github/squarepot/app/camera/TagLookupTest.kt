// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import io.github.squarepot.app.data.PlantView
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import org.junit.Assert.assertEquals
import org.junit.Test

class TagLookupTest {
    private val scope = TestScope()
    private val calls = mutableListOf<String>()
    private var published = 0

    private fun plant(tag: String) = PlantView(id = "p$tag", tag = tag, collectionName = "Main", fields = emptyList())

    private val lookup = TagLookup(
        scope,
        lookup = { number ->
            calls += number
            if (number == "999999") emptyList() else listOf(plant(number))
        },
        onResult = { published++ },
    )

    @Test
    fun `each number is looked up once and published`() {
        lookup.request(listOf("004217", "999999"))
        lookup.request(listOf("004217"))
        scope.runCurrent()
        assertEquals(listOf("004217", "999999"), calls)
        assertEquals(listOf(plant("004217")), lookup.results["004217"])
        assertEquals(emptyList<PlantView>(), lookup.results["999999"])
        assertEquals(2, published)
    }

    @Test
    fun `invalidate forgets answers so numbers are looked up again`() {
        lookup.request(listOf("004217"))
        scope.runCurrent()
        lookup.invalidate()
        assertEquals(emptyMap<String, List<PlantView>>(), lookup.results)
        lookup.request(listOf("004217"))
        scope.runCurrent()
        assertEquals(listOf("004217", "004217"), calls)
    }

    @Test
    fun `an answer started before invalidate is dropped`() {
        val gate = CompletableDeferred<Unit>()
        val slow = TagLookup(
            scope,
            lookup = {
                gate.await()
                listOf(plant(it))
            },
            onResult = { published++ },
        )
        slow.request(listOf("004217"))
        scope.runCurrent()
        slow.invalidate()
        gate.complete(Unit)
        scope.runCurrent()
        assertEquals(emptyMap<String, List<PlantView>>(), slow.results)
        assertEquals(0, published)
    }
}
