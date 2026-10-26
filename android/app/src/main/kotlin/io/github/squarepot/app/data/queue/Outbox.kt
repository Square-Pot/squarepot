// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data.queue

import io.github.squarepot.app.data.api.SightingKind
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext
import java.io.File
import java.util.UUID

/**
 * Where the owner's actions on a plant's card wait to be sent: sightings and photos (ADR 0008).
 * Adding cannot conflict with anything, so it works offline; [onAdded] asks for them to be sent.
 */
class Outbox(
    private val dao: QueueDao,
    private val photoDir: File,
    private val onAdded: () -> Unit,
    private val clock: () -> Long = System::currentTimeMillis,
    private val newId: () -> String = { UUID.randomUUID().toString() },
) {
    /** Items not yet on the server, those with a problem included. */
    val waiting: Flow<Int> = dao.observeWaiting()

    /** Items the server refused, which wait for the owner. */
    val problems: Flow<Int> = dao.observeProblems()

    /** Records that plant [tag] was seen now: marked as seen without a photo, or given a status. */
    suspend fun seen(tag: String, kind: SightingKind) {
        dao.addSighting(QueuedSighting(newId(), tag, clock(), kind))
        onAdded()
    }

    /** Queues the JPEG [photo] of plant [tag], taken at [takenAt], moving the file into the queue. */
    suspend fun addPhoto(tag: String, photo: File, takenAt: Long, comment: String?) {
        val id = newId()
        val file = File(photoDir, "$id.jpg")
        withContext(Dispatchers.IO) {
            photoDir.mkdirs()
            if (!photo.renameTo(file)) {
                photo.copyTo(file)
                photo.delete()
            }
        }
        dao.addPhoto(QueuedPhoto(id, tag, file.name, takenAt, comment?.trim()?.ifEmpty { null }))
        onAdded()
    }

    /** Numbers seen since [since] (epoch millis) by this phone, whether sent yet or not. */
    fun seenSince(since: Long): Flow<Set<String>> = dao.observeSeenSince(since).map { it.toSet() }

    suspend fun hasPending(): Boolean = dao.pendingCount() > 0

    /** Everything not yet on the server, oldest first, for the queue screen. */
    val items: Flow<List<QueueItem>> = combine(dao.observeWaitingPhotos(), dao.observeWaitingSightings()) { p, s ->
        (p.map { QueueItem.Photo(it) } + s.map { QueueItem.Sighting(it) }).sortedBy { it.at }
    }

    /** Sends [item] again, after the owner fixed what the server refused. */
    suspend fun retry(item: QueueItem) {
        when (item) {
            is QueueItem.Photo -> dao.retryPhoto(item.photo.id)
            is QueueItem.Sighting -> dao.retrySighting(item.sighting.id)
        }
        onAdded()
    }

    /** Drops [item] from the queue, with its photo's file. */
    suspend fun discard(item: QueueItem) {
        when (item) {
            is QueueItem.Photo -> {
                dao.deletePhoto(item.photo.id)
                withContext(Dispatchers.IO) { File(photoDir, item.photo.file).delete() }
            }

            is QueueItem.Sighting -> dao.deleteSighting(item.sighting.id)
        }
    }
}

/** One thing waiting to be sent. */
sealed interface QueueItem {
    val tag: String
    val at: Long
    val problem: QueueProblem?

    data class Photo(val photo: QueuedPhoto) : QueueItem {
        override val tag get() = photo.tag
        override val at get() = photo.takenAt
        override val problem get() = photo.problem
    }

    data class Sighting(val sighting: QueuedSighting) : QueueItem {
        override val tag get() = sighting.tag
        override val at get() = sighting.seenAt
        override val problem get() = sighting.problem
    }
}
