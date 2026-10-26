// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import io.github.squarepot.app.data.api.SquarepotApi
import io.github.squarepot.app.data.local.PlantEntity
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** Status for many plants against a fake server: per collection, in batches, and its refusals. */
class StatusEditorTest {
    private val server = MockWebServer()
    private lateinit var api: SquarepotApi
    private val editor = StatusEditor()

    @Before
    fun setUp() {
        server.start()
        api = SquarepotApi(server.url("/"), "secret", OkHttpClient())
    }

    @After
    fun tearDown() = server.close()

    private fun respond(body: String, code: Int = 200) = server.enqueue(
        MockResponse.Builder().code(code).body(body).build(),
    )

    private fun plant(id: String, collection: String = "main", status: String? = null) = PlantEntity(
        id = id,
        collectionId = collection,
        tag = id.padStart(6, '0'),
        sheetRow = 2,
        fields = listOfNotNull("genus" to "Lithops", status?.let { "status" to it }).toMap(),
        custom = emptyMap(),
    )

    private fun results(vararg pairs: Pair<String, String>) =
        pairs.joinToString(prefix = "[", postfix = "]") { (id, result) -> """{"id": "$id", "result": "$result"}""" }

    @Test
    fun `one request per collection, each plant with the status the copy has`() = runTest {
        respond(results("1" to "written", "2" to "changed_in_sheet"))
        respond(results("3" to "not_found"))

        val outcome = editor.set(api, listOf(plant("1"), plant("2", status = "lost"), plant("3", "other")), "lost")

        assertEquals(StatusOutcome.Done(written = 1, changed = 1, missing = 1), outcome)
        val main = server.takeRequest()
        assertEquals("POST", main.method)
        assertEquals("/api/v1/collections/main/status", main.url.encodedPath)
        val body = main.body!!.utf8()
        assertTrue(body, """"status":"lost"""" in body)
        assertTrue(body, """{"id":"1","seen":null}""" in body)
        assertTrue(body, """{"id":"2","seen":"lost"}""" in body)
        assertEquals("/api/v1/collections/other/status", server.takeRequest().url.encodedPath)
    }

    @Test
    fun `more plants than a request takes go in several`() = runTest {
        respond("[]")
        respond("[]")
        editor.set(api, (1..SquarepotApi.MAX_STATUS_PLANTS + 1).map { plant("$it") }, "lost")
        assertEquals(2, server.requestCount)
    }

    @Test
    fun `an empty status clears it`() = runTest {
        respond(results("1" to "written"))
        editor.set(api, listOf(plant("1", status = "lost")), "")
        assertTrue(""""status":null""" in server.takeRequest().body!!.utf8())
    }

    @Test
    fun `a collection read by link is not editable`() = runTest {
        respond("""{"code": "not_editable", "message": "Read by link.", "plant": null}""", code = 409)
        val outcome = editor.set(api, listOf(plant("1")), "lost")
        assertEquals(StatusFailure.NOT_EDITABLE, (outcome as StatusOutcome.Failed).failure)
    }

    @Test
    fun `a refused value says why, and what was written before stays counted`() = runTest {
        respond(results("1" to "written"))
        respond("""{"code": "unprocessable", "message": "The sheet has no status column."}""", code = 422)

        val outcome = editor.set(api, listOf(plant("1"), plant("2", "other")), "lost")

        val written = StatusOutcome.Done(written = 1, changed = 0, missing = 0)
        assertEquals(StatusOutcome.Failed(StatusFailure.REJECTED, "The sheet has no status column.", written), outcome)
    }

    @Test
    fun `without a network nothing is written`() = runTest {
        server.close()
        val outcome = editor.set(api, listOf(plant("1")), "lost")
        assertEquals(StatusFailure.NETWORK, (outcome as StatusOutcome.Failed).failure)
    }
}
