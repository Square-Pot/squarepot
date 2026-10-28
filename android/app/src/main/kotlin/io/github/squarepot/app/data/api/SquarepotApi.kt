// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import okhttp3.HttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
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

    /** Records [sightings], at most [MAX_SIGHTINGS]; each comes back with what the server did with it. */
    suspend fun recordSightings(sightings: List<SightingDto>): List<SightingResultDto> = send(
        request(url("sightings")).post(json(SightingBatchDto.serializer(), SightingBatchDto(sightings))),
        ListSerializer(SightingResultDto.serializer()),
    )

    /**
     * Uploads the JPEG [photo] of plant [tag] as photo [id], taken at [takenAt] (ISO 8601) unless the
     * camera recorded the time, with the owner's [comment]. Sending the same [id] again changes
     * nothing and returns the photo.
     */
    suspend fun uploadPhoto(id: String, tag: String, takenAt: String, comment: String?, photo: File): PhotoDto {
        val url = url("photos", id) {
            addQueryParameter("tag", tag)
            addQueryParameter("taken_at", takenAt)
            if (comment != null) addQueryParameter("comment", comment)
        }
        return send(request(url).put(photo.asRequestBody(JPEG)), PhotoDto.serializer())
    }

    /** Sets [status] (null clears it) for [plants] of [collectionId], at most [MAX_STATUS_PLANTS]; needs `editable`. */
    suspend fun setStatus(collectionId: String, status: String?, plants: List<StatusSeenDto>): List<StatusResultDto> =
        send(
            request(url("collections", collectionId, "status"))
                .post(json(BulkStatusDto.serializer(), BulkStatusDto(status, plants = plants))),
            ListSerializer(StatusResultDto.serializer()),
        )

    private suspend fun <T> get(path: String, serializer: KSerializer<T>, query: HttpUrl.Builder.() -> Unit = {}): T =
        send(request(url(path, query = query)), serializer)

    private fun url(vararg segments: String, query: HttpUrl.Builder.() -> Unit = {}): HttpUrl =
        base.newBuilder().apply { segments.forEach { addPathSegment(it) } }.apply(query).build()

    private fun request(url: HttpUrl) = Request.Builder()
        .url(url)
        .header("Authorization", "Bearer $token")
        .header("Accept", "application/json")

    private suspend fun <T> send(builder: Request.Builder, serializer: KSerializer<T>): T {
        val request = builder.build()
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
            throw ApiException(BAD_RESPONSE, null, "Unexpected response from ${request.url.encodedPath}", e)
        }
    }

    companion object {
        /** [ApiException.status] for a successful response the app could not read. */
        const val BAD_RESPONSE = 0

        /** Most sightings one request takes. */
        const val MAX_SIGHTINGS = 500

        /** Most plants one status request takes. */
        const val MAX_STATUS_PLANTS = 500
    }
}

private val JSON = "application/json".toMediaType()
private val JPEG = "image/jpeg".toMediaType()

/** Request bodies spell out nulls: the server requires keys such as `status` and `seen` even when null. */
private val RequestJson = Json(ApiJson) { explicitNulls = true }

private fun <T> json(serializer: KSerializer<T>, value: T) =
    RequestJson.encodeToString(serializer, value).toRequestBody(JSON)

/** An error response ([status] and the server's [code]), or an unreadable response (status 0). */
class ApiException(val status: Int, val code: String?, message: String, cause: Throwable? = null) :
    IOException(message, cause) {
    val isUnauthorized get() = status == HTTP_UNAUTHORIZED
    val isRateLimited get() = status == HTTP_TOO_MANY_REQUESTS

    companion object {
        private const val HTTP_UNAUTHORIZED = 401
        private const val HTTP_TOO_MANY_REQUESTS = 429

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
