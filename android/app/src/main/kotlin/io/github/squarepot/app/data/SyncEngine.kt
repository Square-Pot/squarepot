// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import androidx.room.withTransaction
import io.github.squarepot.app.data.api.ApiException
import io.github.squarepot.app.data.api.ApiJson
import io.github.squarepot.app.data.api.CollectionDto
import io.github.squarepot.app.data.api.FieldSchemaDto
import io.github.squarepot.app.data.api.PlantDto
import io.github.squarepot.app.data.api.SquarepotApi
import io.github.squarepot.app.data.api.SyncKind
import io.github.squarepot.app.data.api.SyncResponse
import io.github.squarepot.app.data.local.CollectionEntity
import io.github.squarepot.app.data.local.CopyDatabase
import io.github.squarepot.app.data.local.PlantEntity
import io.github.squarepot.app.data.local.SyncStateEntity
import java.io.IOException
import java.net.UnknownServiceException
import java.time.OffsetDateTime
import java.time.format.DateTimeParseException

/** Why a sync failed, stored by name in [SyncStateEntity.failure]. */
enum class SyncFailure {
    /** The server rejected the token. */
    UNAUTHORIZED,

    /** No connection, or the server could not be reached. */
    NETWORK,

    /** The server answered with an error. */
    SERVER,

    /** The server answered with something the app cannot read. */
    BAD_RESPONSE,

    /** The address is http://, and this build allows HTTPS only. */
    CLEARTEXT,
    ;

    companion object {
        /** The failure behind [e], from a request sent over plain HTTP when [cleartext]. */
        fun of(e: IOException, cleartext: Boolean) = when {
            e is ApiException && e.isUnauthorized -> UNAUTHORIZED
            e is ApiException && e.status == SquarepotApi.BAD_RESPONSE -> BAD_RESPONSE
            e is ApiException -> SERVER
            // OkHttp throws this when the network security config forbids cleartext traffic, and
            // also when TLS versions or cipher suites don't match: only the first is CLEARTEXT.
            e is UnknownServiceException && cleartext -> CLEARTEXT
            else -> NETWORK
        }
    }
}

sealed interface SyncOutcome {
    data class Updated(val kind: SyncKind) : SyncOutcome

    data class Failed(val failure: SyncFailure) : SyncOutcome

    /** No server address or token yet; nothing was attempted. */
    data object NotConfigured : SyncOutcome
}

/**
 * Brings the local copy up to date with the server (ADR 0005).
 *
 * One sync is one request to `/sync` with the stored cursor, plus `/schema` when the schema
 * version differs from the stored one. The response and the new cursor are written in one
 * transaction, so an interrupted sync leaves the previous copy and cursor intact. A failed sync
 * changes nothing but the recorded failure: the camera keeps working from the old copy.
 */
class SyncEngine(private val db: CopyDatabase, private val clock: () -> Long = System::currentTimeMillis) {
    private val dao = db.copy()

    suspend fun sync(api: SquarepotApi): SyncOutcome {
        val state = dao.state() ?: SyncStateEntity()
        return try {
            val changes = api.sync(state.cursor)
            val schema = if (changes.schemaVersion != state.schemaVersion || state.schemaJson == null) {
                api.schema()
            } else {
                null
            }
            apply(state, changes, schema)
            SyncOutcome.Updated(changes.kind)
        } catch (e: IOException) {
            fail(state, SyncFailure.of(e, api.isCleartext))
        }
    }

    /** Forgets the cursor, so the next sync downloads a full copy (as after a server change). */
    suspend fun forgetCursor() {
        dao.state()?.let { dao.saveState(it.copy(cursor = null)) }
    }

    private suspend fun apply(state: SyncStateEntity, changes: SyncResponse, schema: FieldSchemaDto?) {
        val now = clock()
        db.withTransaction {
            when (changes.kind) {
                SyncKind.FULL -> {
                    dao.deleteAllPlants()
                    dao.deleteAllCollections()
                }

                SyncKind.DELTA -> {
                    changes.removedPlants.chunked(SQL_VARIABLES).forEach { dao.deletePlants(it) }
                    changes.removedCollections.chunked(SQL_VARIABLES).forEach { dao.deleteCollections(it) }
                }
            }
            dao.upsertCollections(changes.collections.map { it.toEntity() })
            dao.upsertPlants(changes.plants.map { it.toEntity() })
            dao.saveState(
                state.copy(
                    cursor = changes.cursor,
                    schemaVersion = schema?.version ?: state.schemaVersion,
                    schemaJson = schema?.let { ApiJson.encodeToString(FieldSchemaDto.serializer(), it) }
                        ?: state.schemaJson,
                    refreshedAt = now,
                    attemptedAt = now,
                    failure = null,
                ),
            )
        }
    }

    private suspend fun fail(state: SyncStateEntity, failure: SyncFailure): SyncOutcome {
        dao.saveState(state.copy(attemptedAt = clock(), failure = failure.name))
        return SyncOutcome.Failed(failure)
    }

    private companion object {
        /** Ids per DELETE, below SQLite's limit of 999 bound variables on older Android. */
        const val SQL_VARIABLES = 500
    }
}

private fun CollectionDto.toEntity() = CollectionEntity(
    id = id,
    name = name,
    plantCount = plantCount,
    serverSyncedAt = syncedAt?.let(::epochMillis),
    serverError = error,
    customColumns = customColumns,
)

private fun PlantDto.toEntity() = PlantEntity(
    id = id,
    collectionId = collectionId,
    tag = tag,
    sheetRow = row,
    fields = fields,
    custom = custom,
)

private fun epochMillis(timestamp: String): Long? = try {
    OffsetDateTime.parse(timestamp).toInstant().toEpochMilli()
} catch (_: DateTimeParseException) {
    null
}
