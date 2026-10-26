// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data.queue

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import io.github.squarepot.app.data.api.ApiException
import io.github.squarepot.app.data.api.SightingKind

/** Why a queued item was not sent; it waits for the owner to retry or discard it. */
enum class QueueProblem {
    /** No plant has the number. */
    UNKNOWN_NUMBER,

    /** The photo is larger than the server takes. */
    TOO_LARGE,

    /** The server refused the photo: not an image it reads, or an id it has for another plant. */
    REJECTED,

    /** The photo's file is gone from the phone. */
    MISSING_FILE,
    ;

    companion object {
        private const val HTTP_NOT_FOUND = 404
        private const val HTTP_TOO_LARGE = 413
        private const val HTTP_UNPROCESSABLE = 422

        /** The problem of the item itself behind [e], or null when [e] is the server's or the network's. */
        fun of(e: ApiException): QueueProblem? = when (e.status) {
            HTTP_NOT_FOUND -> UNKNOWN_NUMBER
            HTTP_TOO_LARGE -> TOO_LARGE
            HTTP_UNPROCESSABLE -> REJECTED
            else -> null
        }
    }
}

/** A photo of a numbered plant, kept on the phone until it and its comment are on the server (ADR 0007). */
@Entity(tableName = "photos", indices = [Index("sentAt")])
data class QueuedPhoto(
    /** The client's id: uploading it again changes nothing. */
    @PrimaryKey val id: String,
    val tag: String,
    /** The JPEG's name in the queue's folder; the file is deleted once sent. */
    val file: String,
    /** When the photo was taken, epoch millis. */
    val takenAt: Long,
    /** The owner's comment, or null. */
    val comment: String?,
    /** The photo is on the server; only its comment may still be waiting. */
    val uploaded: Boolean = false,
    /** When the photo and its comment reached the server, epoch millis; null while queued. */
    val sentAt: Long? = null,
    val problem: QueueProblem? = null,
    /** The server's words for [problem], in English. */
    val problemMessage: String? = null,
)

/** A sighting without a photo (ADR 0008), kept on the phone until the server has it. */
@Entity(tableName = "sightings", indices = [Index("sentAt")])
data class QueuedSighting(
    /** The client's id: sending it again records nothing twice. */
    @PrimaryKey val id: String,
    val tag: String,
    /** When the plant was seen, epoch millis. */
    val seenAt: Long,
    val kind: SightingKind,
    /** When the server took it, epoch millis; null while queued. */
    val sentAt: Long? = null,
    val problem: QueueProblem? = null,
)
