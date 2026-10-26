// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import android.content.Context
import androidx.datastore.preferences.preferencesDataStore
import io.github.squarepot.app.data.api.CollectionDto
import io.github.squarepot.app.data.api.SquarepotApi
import io.github.squarepot.app.data.local.CopyDatabase
import io.github.squarepot.app.data.queue.Outbox
import io.github.squarepot.app.data.queue.QueueDatabase
import io.github.squarepot.app.data.queue.QueueOutcome
import io.github.squarepot.app.data.queue.QueueSender
import io.github.squarepot.app.data.queue.QueueWorker
import okhttp3.OkHttpClient
import java.io.File
import java.util.concurrent.TimeUnit

private val Context.settingsDataStore by preferencesDataStore(name = "settings")

/** The app's long-lived objects, created once in [io.github.squarepot.app.SquarepotApplication]. */
class AppContainer(context: Context) {
    private val app = context.applicationContext
    val database = CopyDatabase.open(context)
    val queueDatabase = QueueDatabase.open(context)
    val settings = SettingsStore(context.settingsDataStore)
    val captions = CaptionSettingsStore(context.settingsDataStore)
    val localCopy = LocalCopy(database.copy())

    private val photoDir = File(context.filesDir, "queue/photos")
    val outbox = Outbox(queueDatabase.queue(), photoDir, onAdded = { QueueWorker.enqueue(app) })
    private val sender = QueueSender(
        queueDatabase.queue(),
        photoDir,
        inCopy = { database.copy().plantsByTag(it).isNotEmpty() },
    )

    private val engine = SyncEngine(database)
    private val http = OkHttpClient.Builder()
        .connectTimeout(CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .callTimeout(CALL_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .build()

    /** A phone photo is a few megabytes; allow for a slow connection in the greenhouse. */
    private val uploads = http.newBuilder().callTimeout(UPLOAD_TIMEOUT_MINUTES, TimeUnit.MINUTES).build()

    /** Syncs the local copy with the configured server. */
    suspend fun sync(): SyncOutcome = api(settings.current())?.let { engine.sync(it) } ?: SyncOutcome.NotConfigured

    /** Sends the queued photos and sightings to the configured server. */
    suspend fun sendQueue(): QueueOutcome =
        apiFor(settings.current(), uploads)?.let { sender.send(it) } ?: QueueOutcome.NotConfigured

    /** Saves the server settings; a different server address starts the copy over with a full sync. */
    suspend fun saveSettings(new: ServerSettings) {
        val old = settings.current()
        settings.save(new)
        if (old.baseUrl != new.baseUrl) engine.forgetCursor()
        // A queue stopped by a rejected token goes on with the new settings.
        QueueWorker.enqueue(app)
    }

    /** Checks [candidate] by listing its collections, without saving it or touching the copy. */
    suspend fun check(candidate: ServerSettings): List<CollectionDto>? = api(candidate)?.collections()

    private fun api(settings: ServerSettings): SquarepotApi? = apiFor(settings, http)

    private companion object {
        const val CONNECT_TIMEOUT_SECONDS = 15L

        /** A full copy is a few megabytes of JSON; allow for a slow connection. */
        const val CALL_TIMEOUT_SECONDS = 120L

        const val UPLOAD_TIMEOUT_MINUTES = 10L
    }
}

/** A client for [settings], or null when they cannot be used (see [ServerSettings.problem]). */
fun apiFor(settings: ServerSettings, http: OkHttpClient): SquarepotApi? {
    val url = settings.baseUrl
    return if (url != null && settings.isComplete) SquarepotApi(url, settings.token.trim(), http) else null
}
