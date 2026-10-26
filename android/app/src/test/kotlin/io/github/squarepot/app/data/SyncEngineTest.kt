// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import android.app.Application
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import io.github.squarepot.app.data.api.SquarepotApi
import io.github.squarepot.app.data.api.SyncKind
import io.github.squarepot.app.data.local.CopyDatabase
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.net.UnknownServiceException

/** Sync against a fake server: full and delta copies, schema changes, stale cursors and failures. */
@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class)
class SyncEngineTest {
    private val server = MockWebServer()
    private lateinit var db: CopyDatabase
    private lateinit var engine: SyncEngine
    private lateinit var api: SquarepotApi
    private val copy get() = LocalCopy(db.copy())
    private var now = 1_000L

    @Before
    fun setUp() {
        server.start()
        db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext(), CopyDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        engine = SyncEngine(db) { now }
        api = SquarepotApi(server.url("/"), "secret", OkHttpClient())
    }

    @After
    fun tearDown() {
        db.close()
        server.close()
    }

    private fun respond(body: String, code: Int = 200) = server.enqueue(
        MockResponse.Builder().code(code).body(body).build(),
    )

    private suspend fun tags(): List<String?> = (1..9).flatMap { copy.plantsByTag("00000$it", "en") }.map { it.tag }

    @Test
    fun `the first sync downloads a full copy and the schema`() = runTest {
        respond(full(cursor = "c1", plants = listOf(plant("p1", "000001"), plant("p2", "000002"))))
        respond(SCHEMA_V1)

        assertEquals(SyncOutcome.Updated(SyncKind.FULL), engine.sync(api))

        val sync = server.takeRequest()
        assertEquals("/api/v1/sync", sync.url.encodedPath)
        assertNull(sync.url.queryParameter("cursor"))
        assertEquals("Bearer secret", sync.headers["Authorization"])
        assertEquals("/api/v1/schema", server.takeRequest().url.encodedPath)

        val state = db.copy().state()!!
        assertEquals("c1", state.cursor)
        assertEquals(1, state.schemaVersion)
        assertEquals(now, state.refreshedAt)
        assertNull(state.failure)
        assertEquals(listOf("000001", "000002"), tags())
    }

    @Test
    fun `lookup reads the local copy with schema labels in the UI language`() = runTest {
        respond(full(cursor = "c1", plants = listOf(plant("p1", "004217", genus = "Lithops"))))
        respond(SCHEMA_V1)
        engine.sync(api)

        val found = copy.plantsByTag("4217", "ru").single()
        assertEquals("004217", found.tag)
        assertEquals("Main", found.collectionName)
        assertEquals(listOf(FieldValue("genus", "Род", "Lithops")), found.fields)
    }

    @Test
    fun `a delta applies upserts and removals and keeps the schema`() = runTest {
        respond(full(cursor = "c1", plants = listOf(plant("p1", "000001"), plant("p2", "000002"))))
        respond(SCHEMA_V1)
        engine.sync(api)
        server.takeRequest()
        server.takeRequest()

        respond(
            sync(
                kind = "delta",
                cursor = "c2",
                plants = listOf(plant("p1", "000001", genus = "Conophytum"), plant("p3", "000003")),
                removedPlants = listOf("p2"),
            ),
        )
        assertEquals(SyncOutcome.Updated(SyncKind.DELTA), engine.sync(api))

        assertEquals("c1", server.takeRequest().url.queryParameter("cursor"))
        assertEquals("no /schema request when the version is unchanged", 3, server.requestCount)
        assertEquals(listOf("000001", "000003"), tags())
        assertEquals("Conophytum", copy.plantsByTag("000001", "en").single().fields.single().value)
        assertEquals("c2", db.copy().state()!!.cursor)
    }

    @Test
    fun `a removed collection goes with the plants listed for it`() = runTest {
        respond(
            full(
                cursor = "c1",
                collections = listOf(collection("main"), collection("seedlings")),
                plants = listOf(plant("p1", "000001"), plant("p2", "000002", collection = "seedlings")),
            ),
        )
        respond(SCHEMA_V1)
        engine.sync(api)

        respond(
            sync(kind = "delta", cursor = "c2", removedCollections = listOf("seedlings"), removedPlants = listOf("p2")),
        )
        engine.sync(api)

        assertEquals(listOf("main"), db.copy().observeCollections().first().map { it.id })
        assertEquals(listOf("000001"), tags())
    }

    @Test
    fun `a change of the server's read time alone updates the collection`() = runTest {
        respond(full(cursor = "c1", plants = listOf(plant("p1", "000001"))))
        respond(SCHEMA_V1)
        engine.sync(api)

        respond(
            sync(
                kind = "delta",
                cursor = "c2",
                collections = listOf(collection("main", syncedAt = "2026-10-13T10:00:00+00:00", error = "sheet gone")),
            ),
        )
        engine.sync(api)

        val main = db.copy().observeCollections().first().single()
        assertEquals(1_791_885_600_000L, main.serverSyncedAt)
        assertEquals("sheet gone", main.serverError)
        assertEquals(listOf("000001"), tags())
    }

    @Test
    fun `custom columns and their values reach the copy`() = runTest {
        respond(
            full(
                cursor = "c1",
                plants = listOf(plant("p1", "000001", custom = """{"Marathon": "yes"}""")),
                collections = listOf(collection("main", customColumns = """["Marathon", "soil"]""")),
            ),
        )
        respond(SCHEMA_V1)
        engine.sync(api)

        assertEquals(mapOf("Marathon" to "yes"), copy.plantsByTag("000001", "en").single().custom)
        val columns = copy.customColumns().first().single()
        assertEquals("Main", columns.name)
        assertEquals(listOf("Marathon", "soil"), columns.customColumns)
    }

    @Test
    fun `a server without custom columns leaves them empty`() = runTest {
        respond(full(cursor = "c1", plants = listOf(plant("p1", "000001"))))
        respond(SCHEMA_V1)
        engine.sync(api)

        assertTrue(copy.plantsByTag("000001", "en").single().custom.isEmpty())
        assertTrue(copy.customColumns().first().single().customColumns.isEmpty())
    }

    @Test
    fun `a new schema version is fetched and the full copy replaces the old one`() = runTest {
        respond(full(cursor = "c1", plants = listOf(plant("p1", "000001"))))
        respond(SCHEMA_V1)
        engine.sync(api)

        respond(full(cursor = "c2", schemaVersion = 2, plants = listOf(plant("p9", "000009"))))
        respond(SCHEMA_V1.replace("\"version\": 1", "\"version\": 2"))
        assertEquals(SyncOutcome.Updated(SyncKind.FULL), engine.sync(api))

        assertEquals(4, server.requestCount)
        assertEquals(2, db.copy().state()!!.schemaVersion)
        assertEquals(listOf("000009"), tags())
    }

    @Test
    fun `a full answer to an old cursor drops what the server no longer has`() = runTest {
        respond(full(cursor = "c1", plants = listOf(plant("p1", "000001"), plant("p2", "000002"))))
        respond(SCHEMA_V1)
        engine.sync(api)

        respond(full(cursor = "c7", plants = listOf(plant("p2", "000002"))))
        engine.sync(api)

        assertEquals(listOf("000002"), tags())
        assertEquals("c7", db.copy().state()!!.cursor)
    }

    @Test
    fun `plants sharing a number are all found`() = runTest {
        respond(full(cursor = "c1", plants = listOf(plant("p1", "000001"), plant("p2", "000001"))))
        respond(SCHEMA_V1)
        engine.sync(api)

        assertEquals(listOf("p1", "p2"), copy.plantsByTag("1", "en").map { it.id })
    }

    @Test
    fun `a rejected token keeps the copy and the cursor`() = runTest {
        respond(full(cursor = "c1", plants = listOf(plant("p1", "000001"))))
        respond(SCHEMA_V1)
        engine.sync(api)

        now = 2_000L
        respond("""{"code": "unauthorized", "message": "Bad token"}""", code = 401)
        assertEquals(SyncOutcome.Failed(SyncFailure.UNAUTHORIZED), engine.sync(api))

        val state = db.copy().state()!!
        assertEquals("c1", state.cursor)
        assertEquals(1_000L, state.refreshedAt)
        assertEquals(2_000L, state.attemptedAt)
        assertEquals("UNAUTHORIZED", state.failure)
        assertEquals(listOf("000001"), tags())
    }

    @Test
    fun `a server that asks to slow down is told apart from a server error`() = runTest {
        respond(full(cursor = "c1", plants = listOf(plant("p1", "000001"))))
        respond(SCHEMA_V1)
        engine.sync(api)

        respond("""{"code": "rate_limited", "message": "Too many requests"}""", code = 429)
        assertEquals(SyncOutcome.Failed(SyncFailure.RATE_LIMITED), engine.sync(api))
        assertEquals("c1", db.copy().state()!!.cursor)
        assertEquals(listOf("000001"), tags())
    }

    @Test
    fun `without a network the copy still answers lookups`() = runTest {
        respond(full(cursor = "c1", plants = listOf(plant("p1", "000001"))))
        respond(SCHEMA_V1)
        engine.sync(api)
        server.close()

        assertEquals(SyncOutcome.Failed(SyncFailure.NETWORK), engine.sync(api))
        assertEquals(listOf("000001"), tags())
    }

    @Test
    fun `an http address in a build that forbids cleartext is not taken for a network failure`() = runTest {
        val blocked = OkHttpClient.Builder()
            .addInterceptor { throw UnknownServiceException("CLEARTEXT communication not permitted") }
            .build()
        val outcome = engine.sync(SquarepotApi(server.url("/"), "secret", blocked))
        assertEquals(SyncOutcome.Failed(SyncFailure.CLEARTEXT), outcome)
        assertEquals("CLEARTEXT", db.copy().state()!!.failure)
    }

    @Test
    fun `a TLS mismatch over https is a network failure, not cleartext`() = runTest {
        val tlsMismatch = OkHttpClient.Builder()
            .addInterceptor { throw UnknownServiceException("Unable to find acceptable protocols") }
            .build()
        val https = "https://plants.example.org/".toHttpUrl()
        val outcome = engine.sync(SquarepotApi(https, "secret", tlsMismatch))
        assertEquals(SyncOutcome.Failed(SyncFailure.NETWORK), outcome)
    }

    @Test
    fun `an unreadable answer changes nothing`() = runTest {
        respond(full(cursor = "c1", plants = listOf(plant("p1", "000001"))))
        respond(SCHEMA_V1)
        engine.sync(api)

        respond("""{"kind": "full"}""")
        assertEquals(SyncOutcome.Failed(SyncFailure.BAD_RESPONSE), engine.sync(api))
        assertEquals("c1", db.copy().state()!!.cursor)
        assertEquals(listOf("000001"), tags())
    }

    @Test
    fun `the copy keeps when a plant was seen and photographed, and which collections are editable`() = runTest {
        val seen = """
            {"id": "p1", "collection_id": "main", "tag": "000001", "row": 2, "fields": {"genus": "Lithops"},
                "status_since": "2026-10-01", "last_seen": "2026-10-26T14:03:11Z", "photo_count": 3,
                "last_photo": "2026-10-20T09:00:00+03:00", "main_photo_id": "6f1c2b9e-3d4a-4e8f-9b7c-1a2d3e4f5a6b"}
        """.trimIndent()
        val editable = """{"id": "main", "name": "Main", "plant_count": 1, "editable": true}"""
        respond(full(cursor = "c1", plants = listOf(seen, plant("p2", "000002")), collections = listOf(editable)))
        respond(SCHEMA_V1)
        engine.sync(api)

        val plants = db.copy().allPlants().associateBy { it.id }
        val p1 = plants.getValue("p1")
        assertEquals("2026-10-01", p1.statusSince)
        assertEquals(1_793_023_391_000L, p1.lastSeen)
        assertEquals(3, p1.photoCount)
        assertEquals(1_792_476_000_000L, p1.lastPhoto)
        assertEquals("6f1c2b9e-3d4a-4e8f-9b7c-1a2d3e4f5a6b", p1.mainPhotoId)
        val p2 = plants.getValue("p2")
        assertNull(p2.lastSeen)
        assertEquals(0, p2.photoCount)
        assertTrue(db.copy().observeCollections().first().single().editable)
    }

    @Test
    fun `a forgotten cursor asks for a full copy`() = runTest {
        respond(full(cursor = "c1", plants = listOf(plant("p1", "000001"))))
        respond(SCHEMA_V1)
        engine.sync(api)
        server.takeRequest()
        server.takeRequest()

        engine.forgetCursor()
        respond(full(cursor = "c2", plants = emptyList()))
        engine.sync(api)

        assertNull(server.takeRequest().url.queryParameter("cursor"))
        assertTrue(tags().isEmpty())
    }
}

/** A collection; [customColumns] is a JSON array, or null to leave the key out as an older server does. */
private fun collection(id: String, syncedAt: String? = null, error: String? = null, customColumns: String? = null) = """
    {"id": "$id", "name": "${id.replaceFirstChar(Char::uppercase)}", "plant_count": 1,
        "synced_at": ${syncedAt?.let { "\"$it\"" } ?: "null"}, "error": ${error?.let { "\"$it\"" } ?: "null"}
        ${customColumns?.let { ", \"custom_columns\": $it" }.orEmpty()}}
""".trimIndent()

/** A plant; [custom] is a JSON object, or null to leave the key out as an older server does. */
private fun plant(
    id: String,
    tag: String?,
    genus: String = "Lithops",
    collection: String = "main",
    custom: String? = null,
) = """
    {"id": "$id", "collection_id": "$collection", "tag": ${tag?.let { "\"$it\"" } ?: "null"}, "row": 2,
        "fields": {"genus": "$genus"}${custom?.let { ", \"custom\": $it" }.orEmpty()}, "future_key": "ignored"}
""".trimIndent()

private fun full(
    cursor: String,
    plants: List<String>,
    schemaVersion: Int = 1,
    collections: List<String> = listOf(collection("main")),
) = sync("full", cursor, schemaVersion, collections, plants)

@Suppress("LongParameterList") // Mirrors the response's fields.
private fun sync(
    kind: String,
    cursor: String,
    schemaVersion: Int = 1,
    collections: List<String> = emptyList(),
    plants: List<String> = emptyList(),
    removedCollections: List<String> = emptyList(),
    removedPlants: List<String> = emptyList(),
) = """
    {"kind": "$kind", "cursor": "$cursor", "schema_version": $schemaVersion,
        "collections": [${collections.joinToString()}],
        "removed_collections": [${removedCollections.joinToString { "\"$it\"" }}],
        "plants": [${plants.joinToString()}],
        "removed_plants": [${removedPlants.joinToString { "\"$it\"" }}]}
""".trimIndent()

private val SCHEMA_V1 = """
    {"version": 1,
        "fields": [
        {"key": "tag", "type": "text", "label": {"en": "Tag", "ru": "Бирка"}, "group": "basic",
        "pattern": "^(?!000000)[0-9]{6}$"},
        {"key": "genus", "type": "text", "label": {"en": "Genus", "ru": "Род"}, "group": "basic", "required": true,
        "display": {"italic": true, "case": "title"}}
        ],
        "computed": [{"key": "name", "label": {"en": "Name", "ru": "Название"}, "from": ["genus"]}],
        "presets": [{"key": "overlay", "label": {"en": "Camera overlay", "ru": "Подпись в кадре"}, "fields": ["name"]}]}
""".trimIndent()
