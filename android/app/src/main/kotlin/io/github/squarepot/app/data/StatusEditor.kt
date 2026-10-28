// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data

import io.github.squarepot.app.data.api.ApiException
import io.github.squarepot.app.data.api.SquarepotApi
import io.github.squarepot.app.data.api.StatusSeenDto
import io.github.squarepot.app.data.local.PlantEntity
import java.io.IOException

/** Why a status was not written. */
enum class StatusFailure {
    /** The collection is read by link: only a service account can write to the sheet (ADR 0006). */
    NOT_EDITABLE,

    /** The server refused the value, or the sheet has no `status` column; [StatusOutcome.Failed.message] says which. */
    REJECTED,

    UNAUTHORIZED,
    NETWORK,
    SERVER,
    RATE_LIMITED,
    CLEARTEXT,
    BAD_RESPONSE,
}

sealed interface StatusOutcome {
    /** How many plants were [written], [changed] in the sheet since the copy (not written), or [missing]. */
    data class Done(val written: Int, val changed: Int, val missing: Int) : StatusOutcome

    /** Nothing more was written after [failure]; [done] counts what was before it. */
    data class Failed(val failure: StatusFailure, val message: String?, val done: Done) : StatusOutcome

    /** No server address or token yet. */
    data object NotConfigured : StatusOutcome
}

/** How many plants the server wrote, before a failure too. */
val StatusOutcome.written: Int
    get() = when (this) {
        is StatusOutcome.Done -> written
        is StatusOutcome.Failed -> done.written
        StatusOutcome.NotConfigured -> 0
    }

/** The keys of `status` in the order the apps offer them: a plant a walk did not find is `lost` first. */
val STATUS_ORDER = listOf("lost", "dead", "gifted", "sold")

/**
 * Sets one status for many plants (ADR 0008): one request per collection and per 500 plants,
 * each plant with the status the copy has for it, so a cell changed in the sheet meanwhile is
 * kept. Edits need the server (ADR 0006): nothing is queued.
 */
class StatusEditor {
    suspend fun set(api: SquarepotApi, plants: List<PlantEntity>, status: String?): StatusOutcome {
        var done = StatusOutcome.Done(0, 0, 0)
        val batches = plants.groupBy { it.collectionId }.flatMap { (collection, members) ->
            members.chunked(SquarepotApi.MAX_STATUS_PLANTS).map { collection to it }
        }
        for ((collection, batch) in batches) {
            // What the sheet's cell holds: the status, or the text the import rejected, which the server compares too.
            val seen = batch.map { StatusSeenDto(it.id, it.fields[STATUS] ?: it.rejectedStatus) }
            val results = try {
                api.setStatus(collection, status?.ifEmpty { null }, seen)
            } catch (e: IOException) {
                return StatusOutcome.Failed(failureOf(e, api.isCleartext), (e as? ApiException)?.message, done)
            }
            done = done.copy(
                written = done.written + results.count { it.result == WRITTEN },
                changed = done.changed + results.count { it.result == CHANGED },
                missing = done.missing + results.count { it.result != WRITTEN && it.result != CHANGED },
            )
        }
        return done
    }

    private fun failureOf(e: IOException, cleartext: Boolean): StatusFailure = when {
        e is ApiException && e.status == HTTP_CONFLICT && e.code == NOT_EDITABLE -> StatusFailure.NOT_EDITABLE
        e is ApiException && e.status == HTTP_UNPROCESSABLE -> StatusFailure.REJECTED
        else -> when (SyncFailure.of(e, cleartext)) {
            SyncFailure.UNAUTHORIZED -> StatusFailure.UNAUTHORIZED
            SyncFailure.NETWORK -> StatusFailure.NETWORK
            SyncFailure.SERVER -> StatusFailure.SERVER
            SyncFailure.RATE_LIMITED -> StatusFailure.RATE_LIMITED
            SyncFailure.CLEARTEXT -> StatusFailure.CLEARTEXT
            SyncFailure.BAD_RESPONSE -> StatusFailure.BAD_RESPONSE
        }
    }

    private companion object {
        const val STATUS = "status"
        const val WRITTEN = "written"
        const val CHANGED = "changed_in_sheet"
        const val NOT_EDITABLE = "not_editable"
        const val HTTP_CONFLICT = 409
        const val HTTP_UNPROCESSABLE = 422
    }
}
