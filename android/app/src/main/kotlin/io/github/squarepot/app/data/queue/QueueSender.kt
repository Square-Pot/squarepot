// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data.queue

import io.github.squarepot.app.data.SyncFailure
import io.github.squarepot.app.data.api.ApiException
import io.github.squarepot.app.data.api.SightingDto
import io.github.squarepot.app.data.api.SquarepotApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import java.time.Instant
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

sealed interface QueueOutcome {
    /** Everything that could be sent was; [sent] items reached the server. */
    data class Done(val sent: Int) : QueueOutcome

    /** Sending stopped at [failure], after [sent] items reached the server. */
    data class Failed(val failure: SyncFailure, val sent: Int) : QueueOutcome

    /** No server address or token yet; nothing was attempted. */
    data object NotConfigured : QueueOutcome
}

/**
 * Sends the queue: sightings in batches, then photos one at a time, each followed by its comment.
 *
 * Every item has the client's id, so sending it again after a lost answer is harmless. A refusal
 * that is the item's own (a number no plant has, a photo too large or unreadable) is kept on the
 * item for the owner, and the rest of the queue goes on. Any other failure stops sending, and
 * everything not sent stays queued for the next attempt.
 */
class QueueSender(
    private val dao: QueueDao,
    private val photoDir: File,
    private val clock: () -> Long = System::currentTimeMillis,
) {
    suspend fun send(api: SquarepotApi): QueueOutcome {
        val sent = AtomicInteger()
        return try {
            sendSightings(api, sent)
            sendPhotos(api, sent)
            val before = clock() - KEEP_SENT_MILLIS
            dao.forgetSightingsSentBefore(before)
            dao.forgetPhotosSentBefore(before)
            QueueOutcome.Done(sent.get())
        } catch (e: IOException) {
            QueueOutcome.Failed(SyncFailure.of(e, api.isCleartext), sent.get())
        }
    }

    private suspend fun sendSightings(api: SquarepotApi, sent: AtomicInteger) {
        var batch = dao.pendingSightings(SquarepotApi.MAX_SIGHTINGS)
        while (batch.isNotEmpty()) {
            val dtos = batch.map { SightingDto(it.id, it.tag, Instant.ofEpochMilli(it.seenAt).toString(), it.kind) }
            val unknown = api.recordSightings(dtos).filter { it.result == NO_SUCH_NUMBER }.map { it.id }.toSet()
            val taken = batch.map { it.id }.filter { it !in unknown }
            dao.markSightingsSent(taken, clock())
            if (unknown.isNotEmpty()) dao.markSightingsProblem(unknown.toList(), QueueProblem.UNKNOWN_NUMBER)
            sent.addAndGet(taken.size)
            batch = dao.pendingSightings(SquarepotApi.MAX_SIGHTINGS)
        }
    }

    private suspend fun sendPhotos(api: SquarepotApi, sent: AtomicInteger) {
        for (photo in dao.pendingPhotos()) {
            if (sendPhoto(api, photo)) sent.incrementAndGet()
        }
    }

    /** Sends [photo], then its comment; returns whether both reached the server. */
    private suspend fun sendPhoto(api: SquarepotApi, photo: QueuedPhoto): Boolean {
        val file = File(photoDir, photo.file)
        if (!photo.uploaded && !withContext(Dispatchers.IO) { file.exists() }) {
            dao.updatePhoto(photo.copy(problem = QueueProblem.MISSING_FILE))
            return false
        }
        return try {
            if (!photo.uploaded) {
                api.uploadPhoto(photo.id, photo.tag, Instant.ofEpochMilli(photo.takenAt).toString(), file)
                // Kept at once, so a failed comment does not send the photo again.
                dao.updatePhoto(photo.copy(uploaded = true))
            }
            photo.comment?.let { api.changePhotoComment(photo.id, it) }
            dao.updatePhoto(photo.copy(uploaded = true, sentAt = clock()))
            withContext(Dispatchers.IO) { file.delete() }
            true
        } catch (e: ApiException) {
            val problem = QueueProblem.of(e) ?: throw e
            dao.updatePhoto(photo.copy(problem = problem, problemMessage = e.message))
            false
        }
    }

    private companion object {
        /** `SightingResult.result` for a number no plant has. */
        const val NO_SUCH_NUMBER = "unknown_number"

        /** How long sent items are kept, so a long walk still counts them as seen. */
        val KEEP_SENT_MILLIS = TimeUnit.DAYS.toMillis(90)
    }
}
