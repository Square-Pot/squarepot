// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/** What is wrong with [ServerSettings], for the screen to explain. */
enum class SettingsProblem {
    /** Not an http(s) address. */
    URL,

    /** Empty, or not printable ASCII: an HTTP header cannot carry it. */
    TOKEN,
}

/**
 * The server this phone syncs with, entered by the collector in the app.
 *
 * The token is the operator's API token. It is kept in the app's private storage, which is
 * excluded from backups and device transfer, and is never logged.
 */
data class ServerSettings(val url: String = "", val token: String = "") {
    /** The server's base address, or null when [url] is not a valid http(s) address. */
    val baseUrl: HttpUrl? get() = url.trim().toHttpUrlOrNull()

    /** The first problem with these settings, or null when they can be used. */
    val problem: SettingsProblem?
        get() = when {
            baseUrl == null -> SettingsProblem.URL
            !isValidToken(token.trim()) -> SettingsProblem.TOKEN
            else -> null
        }

    val isComplete: Boolean get() = problem == null
}

/**
 * A token is sent in the Authorization header, which takes printable ASCII only: OkHttp rejects
 * anything else (a Cyrillic letter typed by mistake, say) with an exception, not an HTTP error.
 */
fun isValidToken(token: String): Boolean = token.isNotEmpty() && token.all { it in '!'..'~' }

class SettingsStore(private val dataStore: DataStore<Preferences>) {
    val settings: Flow<ServerSettings> = dataStore.data.map {
        ServerSettings(url = it[URL].orEmpty(), token = it[TOKEN].orEmpty())
    }

    suspend fun current(): ServerSettings = settings.first()

    suspend fun save(settings: ServerSettings) {
        dataStore.edit {
            it[URL] = settings.url.trim()
            it[TOKEN] = settings.token.trim()
        }
    }

    private companion object {
        val URL = stringPreferencesKey("server_url")
        val TOKEN = stringPreferencesKey("server_token")
    }
}
