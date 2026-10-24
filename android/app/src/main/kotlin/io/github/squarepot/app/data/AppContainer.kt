// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import android.content.Context
import androidx.datastore.preferences.preferencesDataStore
import io.github.squarepot.app.data.api.CollectionDto
import io.github.squarepot.app.data.api.SquarepotApi
import io.github.squarepot.app.data.local.CopyDatabase
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

private val Context.settingsDataStore by preferencesDataStore(name = "settings")

/** The app's long-lived objects, created once in [io.github.squarepot.app.SquarepotApplication]. */
class AppContainer(context: Context) {
    val database = CopyDatabase.open(context)
    val settings = SettingsStore(context.settingsDataStore)
    val captions = CaptionSettingsStore(context.settingsDataStore)
    val localCopy = LocalCopy(database.copy())

    private val engine = SyncEngine(database)
    private val http = OkHttpClient.Builder()
        .connectTimeout(CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .callTimeout(CALL_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .build()

    /** Syncs the local copy with the configured server. */
    suspend fun sync(): SyncOutcome = api(settings.current())?.let { engine.sync(it) } ?: SyncOutcome.NotConfigured

    /** Saves the server settings; a different server address starts the copy over with a full sync. */
    suspend fun saveSettings(new: ServerSettings) {
        val old = settings.current()
        settings.save(new)
        if (old.baseUrl != new.baseUrl) engine.forgetCursor()
    }

    /** Checks [candidate] by listing its collections, without saving it or touching the copy. */
    suspend fun check(candidate: ServerSettings): List<CollectionDto>? = api(candidate)?.collections()

    private fun api(settings: ServerSettings): SquarepotApi? = apiFor(settings, http)

    private companion object {
        const val CONNECT_TIMEOUT_SECONDS = 15L

        /** A full copy is a few megabytes of JSON; allow for a slow connection. */
        const val CALL_TIMEOUT_SECONDS = 120L
    }
}

/** A client for [settings], or null when they cannot be used (see [ServerSettings.problem]). */
fun apiFor(settings: ServerSettings, http: OkHttpClient): SquarepotApi? {
    val url = settings.baseUrl
    return if (url != null && settings.isComplete) SquarepotApi(url, settings.token.trim(), http) else null
}
