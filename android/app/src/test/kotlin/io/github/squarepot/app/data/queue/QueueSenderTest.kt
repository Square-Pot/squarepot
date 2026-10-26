// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data.queue

import android.app.Application
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import io.github.squarepot.app.data.SyncFailure
import io.github.squarepot.app.data.api.SightingKind
import io.github.squarepot.app.data.api.SquarepotApi
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.File

/** The queue against a fake server: batches, photos with comments, refusals and failures. */
@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class)
class QueueSenderTest {
    @get:Rule
    val folder = TemporaryFolder()

    private val server = MockWebServer()
    private lateinit var db: QueueDatabase
    private lateinit var dao: QueueDao
    private lateinit var photoDir: File
    private lateinit var outbox: Outbox
    private lateinit var sender: QueueSender
    private lateinit var api: SquarepotApi
    private var now = 1_000L
    private var ids = 0
    private var added = 0

    /** Numbers the local copy has. */
    private val copy = mutableSetOf("004217", "004218", "004219")

    @Before
    fun setUp() {
        server.start()
        db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext(), QueueDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        dao = db.queue()
        photoDir = folder.newFolder("queue")
        outbox = Outbox(dao, photoDir, onAdded = { added++ }, clock = { now }, newId = { "id-${++ids}" })
        sender = QueueSender(dao, photoDir, inCopy = { it in copy }) { now }
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

    private fun shot(name: String = "shot.jpg", bytes: Int = 16) =
        folder.newFile(name).apply { writeBytes(ByteArray(bytes) { it.toByte() }) }

    private fun photoJson(id: String, tag: String) =
        """{"id": "$id", "tag": "$tag", "taken_at": "1970-01-01T00:00:01Z"}"""

    @Test
    fun `sightings go out in one batch and are kept as sent`() = runTest {
        outbox.seen("004217", SightingKind.SEEN)
        now = 2_000L
        outbox.seen("004218", SightingKind.STATUS)
        assertEquals(2, added)
        respond("""[{"id": "id-1", "result": "recorded"}, {"id": "id-2", "result": "already_recorded"}]""")

        assertEquals(QueueOutcome.Done(sent = 2), sender.send(api))

        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/v1/sightings", request.url.encodedPath)
        val body = request.body!!.utf8()
        val first = """{"id":"id-1","tag":"004217","seen_at":"1970-01-01T00:00:01Z","kind":"seen"}"""
        assertTrue(body, first in body)
        assertTrue(body, "\"kind\":\"status\"" in body)
        assertFalse(outbox.hasPending())
        assertEquals(0, outbox.waiting.first())
        assertEquals(setOf("004217", "004218"), outbox.seenSince(0).first())
    }

    @Test
    fun `more sightings than a request takes go out in several`() = runTest {
        repeat(SquarepotApi.MAX_SIGHTINGS + 1) { outbox.seen("004217", SightingKind.SEEN) }
        respond("[]")
        respond("[]")

        assertEquals(QueueOutcome.Done(sent = SquarepotApi.MAX_SIGHTINGS + 1), sender.send(api))
        assertEquals(2, server.requestCount)
    }

    @Test
    fun `a sighting of a number no plant has waits for the owner`() = runTest {
        outbox.seen("999999", SightingKind.SEEN)
        respond("""[{"id": "id-1", "result": "unknown_number"}]""")

        assertEquals(QueueOutcome.Done(sent = 0), sender.send(api))
        assertEquals(1, outbox.problems.first())
        assertFalse(outbox.hasPending())
    }

    @Test
    fun `a photo is uploaded with its comment, and its file is removed`() = runTest {
        outbox.addPhoto("004217", shot(), takenAt = 1_000L, comment = "  first flower ")
        assertFalse(File(folder.root, "shot.jpg").exists())
        respond(photoJson("id-1", "004217"), code = 201)

        assertEquals(QueueOutcome.Done(sent = 1), sender.send(api))

        val upload = server.takeRequest()
        assertEquals("PUT", upload.method)
        assertEquals("/api/v1/photos/id-1", upload.url.encodedPath)
        assertEquals("004217", upload.url.queryParameter("tag"))
        assertEquals("1970-01-01T00:00:01Z", upload.url.queryParameter("taken_at"))
        assertEquals("image/jpeg", upload.headers["Content-Type"])
        assertEquals(16, upload.body!!.size)
        assertEquals("first flower", upload.url.queryParameter("comment"))
        assertEquals(1, server.requestCount)
        assertFalse(File(photoDir, "id-1.jpg").exists())
        assertEquals(0, outbox.waiting.first())
    }

    @Test
    fun `a photo without a comment is sent without one`() = runTest {
        outbox.addPhoto("004217", shot(), takenAt = 1_000L, comment = " ")
        respond(photoJson("id-1", "004217"), code = 201)

        assertEquals(QueueOutcome.Done(sent = 1), sender.send(api))
        assertNull(server.takeRequest().url.queryParameter("comment"))
    }

    @Test
    fun `a photo of a number no plant has waits, and the next one is still sent`() = runTest {
        outbox.addPhoto("999999", shot("a.jpg"), takenAt = 1_000L, comment = null)
        outbox.addPhoto("004217", shot("b.jpg"), takenAt = 2_000L, comment = null)
        respond("""{"code": "not_found", "message": "No plant has the number 999999."}""", code = 404)
        respond(photoJson("id-2", "004217"), code = 201)

        assertEquals(QueueOutcome.Done(sent = 1), sender.send(api))

        val waiting = dao.pendingPhotos()
        assertTrue(waiting.isEmpty())
        assertEquals(1, outbox.problems.first())
        assertTrue("the refused photo is kept", File(photoDir, "id-1.jpg").exists())
    }

    @Test
    fun `a 404 for a plant the copy has is a server too old for photos, retried`() = runTest {
        outbox.addPhoto("004217", shot(), takenAt = 1_000L, comment = null)
        respond("""{"code": "not_found", "message": "Not Found"}""", code = 404)

        assertEquals(QueueOutcome.Failed(SyncFailure.SERVER, sent = 0), sender.send(api))
        assertEquals(1, dao.pendingPhotos().size)
        assertEquals(0, outbox.problems.first())
    }

    @Test
    fun `a photo too large or unreadable waits for the owner`() = runTest {
        outbox.addPhoto("004217", shot("a.jpg"), takenAt = 1_000L, comment = null)
        outbox.addPhoto("004217", shot("b.jpg"), takenAt = 2_000L, comment = null)
        respond("""{"code": "too_large", "message": "The photo is larger than 30 MB."}""", code = 413)
        respond("""{"code": "unprocessable", "message": "Not an image."}""", code = 422)

        assertEquals(QueueOutcome.Done(sent = 0), sender.send(api))
        assertEquals(2, outbox.problems.first())
    }

    @Test
    fun `a server error stops sending and keeps everything queued`() = runTest {
        outbox.addPhoto("004217", shot("a.jpg"), takenAt = 1_000L, comment = null)
        outbox.addPhoto("004218", shot("b.jpg"), takenAt = 2_000L, comment = null)
        respond("""{"code": "unavailable", "message": "Photos cannot be stored."}""", code = 503)

        assertEquals(QueueOutcome.Failed(SyncFailure.SERVER, sent = 0), sender.send(api))
        assertEquals(1, server.requestCount)
        assertEquals(2, dao.pendingPhotos().size)
        assertEquals(0, outbox.problems.first())
    }

    @Test
    fun `a busy server stops sending, to be retried`() = runTest {
        outbox.seen("004217", SightingKind.SEEN)
        respond("""{"code": "rate_limited", "message": "Too many requests"}""", code = 429)

        assertEquals(QueueOutcome.Failed(SyncFailure.RATE_LIMITED, sent = 0), sender.send(api))
        assertTrue(outbox.hasPending())
    }

    @Test
    fun `a photo whose file is gone waits for the owner without a request`() = runTest {
        outbox.addPhoto("004217", shot(), takenAt = 1_000L, comment = null)
        File(photoDir, "id-1.jpg").delete()

        assertEquals(QueueOutcome.Done(sent = 0), sender.send(api))
        assertEquals(0, server.requestCount)
        assertEquals(1, outbox.problems.first())
    }

    @Test
    fun `without a network nothing is lost`() = runTest {
        outbox.seen("004217", SightingKind.SEEN)
        server.close()

        assertEquals(QueueOutcome.Failed(SyncFailure.NETWORK, sent = 0), sender.send(api))
        assertTrue(outbox.hasPending())
        assertEquals(setOf("004217"), outbox.seenSince(0).first())
    }

    @Test
    fun `a walk counts what this phone saw since it began`() = runTest {
        outbox.seen("004217", SightingKind.SEEN)
        now = 5_000L
        outbox.seen("004218", SightingKind.SEEN)
        outbox.addPhoto("004219", shot(), takenAt = 6_000L, comment = null)

        assertEquals(setOf("004218", "004219"), outbox.seenSince(5_000L).first())
    }

    @Test
    fun `a refused item can be retried or discarded`() = runTest {
        outbox.addPhoto("999999", shot("a.jpg"), takenAt = 1_000L, comment = null)
        outbox.seen("999998", SightingKind.SEEN)
        respond("""[{"id": "id-2", "result": "unknown_number"}]""")
        respond("""{"code": "not_found", "message": "No plant has the number 999999."}""", code = 404)
        sender.send(api)
        val (photo, sighting) = outbox.items.first()
        assertEquals(QueueProblem.UNKNOWN_NUMBER, photo.problem)
        assertEquals(QueueProblem.UNKNOWN_NUMBER, sighting.problem)

        val before = added
        outbox.retry(photo)
        assertEquals(before + 1, added)
        assertNull(outbox.items.first().first().problem)
        assertTrue(outbox.hasPending())

        outbox.discard(sighting)
        assertEquals(listOf("id-1"), outbox.items.first().map { (it as QueueItem.Photo).photo.id })
        outbox.discard(outbox.items.first().single())
        assertTrue(outbox.items.first().isEmpty())
        assertFalse("the discarded photo's file is removed", File(photoDir, "id-1.jpg").exists())
    }

    @Test
    fun `sent items are forgotten after a while`() = runTest {
        outbox.seen("004217", SightingKind.SEEN)
        respond("""[{"id": "id-1", "result": "recorded"}]""")
        sender.send(api)

        now += 91L * 24 * 60 * 60 * 1000
        sender.send(api)
        assertTrue(outbox.seenSince(0).first().isEmpty())
        assertNull(dao.pendingSightings(1).firstOrNull())
    }
}
