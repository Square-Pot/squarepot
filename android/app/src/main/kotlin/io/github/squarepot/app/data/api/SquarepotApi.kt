// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
import kotlinx.serialization.builtins.ListSerializer
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException

/**
 * Client for the server's v1 API at [server], authorised with the operator's [token].
 *
 * OkHttp asks for gzip and unpacks it, which matters for a full sync over poor coverage.
 * Network failures surface as [IOException]; error responses as [ApiException].
 */
class SquarepotApi(server: HttpUrl, private val token: String, private val client: OkHttpClient) {
    private val base = server.newBuilder().addPathSegments("api/v1").build()

    /** Whether requests go over plain HTTP. */
    val isCleartext: Boolean = !server.isHttps

    /** Changes since [cursor], or a full copy when [cursor] is null or can no longer be served. */
    suspend fun sync(cursor: String?): SyncResponse = get(
        "sync",
        SyncResponse.serializer(),
    ) { if (cursor != null) addQueryParameter("cursor", cursor) }

    suspend fun schema(): FieldSchemaDto = get("schema", FieldSchemaDto.serializer())

    suspend fun collections(): List<CollectionDto> = get(
        "collections",
        ListSerializer(CollectionDto.serializer()),
    )

    private suspend fun <T> get(path: String, serializer: KSerializer<T>, query: HttpUrl.Builder.() -> Unit = {}): T {
        val url = base.newBuilder().addPathSegment(path).apply(query).build()
        val request = Request.Builder()
            .url(url)
            .header("Authorization", "Bearer $token")
            .header("Accept", "application/json")
            .build()
        val body = withContext(Dispatchers.IO) {
            client.newCall(request).execute().use { response ->
                val text = response.body.string()
                if (!response.isSuccessful) throw ApiException.of(response.code, text)
                text
            }
        }
        // SerializationException is an IllegalArgumentException.
        return try {
            ApiJson.decodeFromString(serializer, body)
        } catch (e: IllegalArgumentException) {
            throw ApiException(BAD_RESPONSE, null, "Unexpected response from $path", e)
        }
    }

    companion object {
        /** [ApiException.status] for a successful response the app could not read. */
        const val BAD_RESPONSE = 0
    }
}

/** An error response ([status] and the server's [code]), or an unreadable response (status 0). */
class ApiException(val status: Int, val code: String?, message: String, cause: Throwable? = null) :
    IOException(message, cause) {
    val isUnauthorized get() = status == HTTP_UNAUTHORIZED

    companion object {
        private const val HTTP_UNAUTHORIZED = 401

        fun of(status: Int, body: String): ApiException {
            val error = try {
                ApiJson.decodeFromString(ErrorDto.serializer(), body)
            } catch (_: IllegalArgumentException) {
                null
            }
            return ApiException(status, error?.code, error?.message ?: "HTTP $status")
        }
    }
}
