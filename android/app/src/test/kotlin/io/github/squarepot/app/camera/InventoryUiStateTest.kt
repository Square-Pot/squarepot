// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.camera

import io.github.squarepot.app.data.InventoryWalk
import io.github.squarepot.app.data.local.PlantEntity
import org.junit.Assert.assertEquals
import org.junit.Test

/** The walk's "not seen" list: in scope, not seen since it began, by number. */
class InventoryUiStateTest {
    private fun plant(tag: String, collection: String = "main", status: String? = null) = PlantEntity(
        id = "p$tag",
        collectionId = collection,
        tag = tag,
        sheetRow = 2,
        fields = listOfNotNull("genus" to "Lithops", status?.let { "status" to it }).toMap(),
        custom = emptyMap(),
    )

    @Test
    fun `not seen are the walk's current plants nobody saw, by number`() {
        val state = InventoryUiState(
            walk = InventoryWalk(collectionId = "main"),
            plants = listOf(
                plant("000003"),
                plant("000001"),
                plant("000002"),
                plant("000004", status = "dead"),
                plant("000005", collection = "other"),
            ),
            seen = setOf("000002"),
        )
        assertEquals(listOf("000001", "000003"), state.notSeen.map { it.tag })
    }
}
