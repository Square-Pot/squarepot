// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import android.app.Application
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import io.github.squarepot.app.data.api.SquarepotApi
import io.github.squarepot.app.data.api.SyncKind
import io.github.squarepot.app.data.local.CopyDatabase
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.File

/**
 * End to end against the server in demo mode (deploy/compose.demo.yaml), run by the Android e2e
 * workflow. Skipped unless SQUAREPOT_E2E_URL, SQUAREPOT_E2E_TOKEN and SQUAREPOT_E2E_CSV (the demo's
 * plants.csv, which the server re-reads every few seconds) are set. Edits the CSV and restores it.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class)
class DemoServerTest {
    private val url = System.getenv("SQUAREPOT_E2E_URL")
    private val token = System.getenv("SQUAREPOT_E2E_TOKEN")
    private val csv = System.getenv("SQUAREPOT_E2E_CSV")?.let(::File)
    private lateinit var original: String
    private lateinit var db: CopyDatabase
    private lateinit var engine: SyncEngine
    private lateinit var api: SquarepotApi
    private val copy get() = LocalCopy(db.copy())

    @Before
    fun setUp() {
        assumeTrue("demo server not configured", url != null && token != null && csv != null)
        original = csv!!.readText()
        db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext(), CopyDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        engine = SyncEngine(db)
        api = SquarepotApi(url!!.toHttpUrl(), token!!, OkHttpClient())
    }

    @After
    fun tearDown() {
        if (!::db.isInitialized) return
        csv!!.writeText(original)
        db.close()
    }

    private suspend fun genus(tag: String) =
        copy.plantsByTag(tag, "en").singleOrNull()?.fields?.firstOrNull { it.key == "genus" }?.value

    /** Syncs until [done], as the server picks up a CSV change within seconds. */
    private suspend fun syncUntil(done: suspend () -> Boolean): List<SyncOutcome> {
        val outcomes = mutableListOf<SyncOutcome>()
        repeat(POLLS) {
            outcomes += engine.sync(api)
            if (done()) return outcomes
            delay(POLL_MILLIS)
        }
        error("no change after ${POLLS * POLL_MILLIS} ms: $outcomes")
    }

    @Test
    fun `the demo copy downloads, then follows edits of the sheet as deltas`() = runBlocking {
        assertEquals(SyncOutcome.Updated(SyncKind.FULL), engine.sync(api))
        assertEquals(DEMO_PLANTS, db.copy().observePlantCount().first())
        assertEquals("Exemplaria", genus("42"))
        assertEquals("Demo plants", copy.plantsByTag("000042", "en").single().collectionName)
        assertTrue(db.copy().observeCollections().first().single().serverSyncedAt != null)

        assertEquals(SyncOutcome.Updated(SyncKind.DELTA), engine.sync(api))
        assertEquals(DEMO_PLANTS, db.copy().observePlantCount().first())

        csv!!.writeText(original.replace("\n000042,,Exemplaria,", "\n000042,,Renamedia,"))
        val edit = syncUntil { genus("42") == "Renamedia" }
        assertTrue(edit.all { it == SyncOutcome.Updated(SyncKind.DELTA) })

        csv.writeText(original.lines().filterNot { it.startsWith("000077,") }.joinToString("\n"))
        val removal = syncUntil { copy.plantsByTag("77", "en").isEmpty() }
        assertTrue(removal.all { it == SyncOutcome.Updated(SyncKind.DELTA) })
        assertEquals(DEMO_PLANTS - 1, db.copy().observePlantCount().first())
    }

    private companion object {
        const val DEMO_PLANTS = 80
        const val POLLS = 30
        const val POLL_MILLIS = 1_000L
    }
}
