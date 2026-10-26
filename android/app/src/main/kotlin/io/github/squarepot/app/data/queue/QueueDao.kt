// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data.queue

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

/** Reads and writes the queue. Sent items stay a while, so a walk still counts them as seen. */
@Suppress("TooManyFunctions")
@Dao
interface QueueDao {
    @Insert
    suspend fun addPhoto(photo: QueuedPhoto)

    @Insert
    suspend fun addSighting(sighting: QueuedSighting)

    @Update
    suspend fun updatePhoto(photo: QueuedPhoto)

    @Query("SELECT * FROM photos WHERE sentAt IS NULL AND problem IS NULL ORDER BY takenAt")
    suspend fun pendingPhotos(): List<QueuedPhoto>

    @Query("SELECT * FROM sightings WHERE sentAt IS NULL AND problem IS NULL ORDER BY seenAt LIMIT :limit")
    suspend fun pendingSightings(limit: Int): List<QueuedSighting>

    @Query(
        "SELECT (SELECT COUNT(*) FROM photos WHERE sentAt IS NULL AND problem IS NULL) + " +
            "(SELECT COUNT(*) FROM sightings WHERE sentAt IS NULL AND problem IS NULL)",
    )
    suspend fun pendingCount(): Int

    @Query("UPDATE sightings SET sentAt = :at WHERE id IN (:ids)")
    suspend fun markSightingsSent(ids: List<String>, at: Long)

    @Query("UPDATE sightings SET problem = :problem WHERE id IN (:ids)")
    suspend fun markSightingsProblem(ids: List<String>, problem: QueueProblem)

    /** Items not yet on the server, those with a problem included. */
    @Query(
        "SELECT (SELECT COUNT(*) FROM photos WHERE sentAt IS NULL) + " +
            "(SELECT COUNT(*) FROM sightings WHERE sentAt IS NULL)",
    )
    fun observeWaiting(): Flow<Int>

    @Query(
        "SELECT (SELECT COUNT(*) FROM photos WHERE sentAt IS NULL AND problem IS NOT NULL) + " +
            "(SELECT COUNT(*) FROM sightings WHERE sentAt IS NULL AND problem IS NOT NULL)",
    )
    fun observeProblems(): Flow<Int>

    /** Numbers seen since [since], sent or not. */
    @Query("SELECT tag FROM sightings WHERE seenAt >= :since UNION SELECT tag FROM photos WHERE takenAt >= :since")
    fun observeSeenSince(since: Long): Flow<List<String>>

    @Query("SELECT * FROM photos WHERE sentAt IS NULL ORDER BY takenAt")
    fun observeWaitingPhotos(): Flow<List<QueuedPhoto>>

    @Query("SELECT * FROM sightings WHERE sentAt IS NULL ORDER BY seenAt")
    fun observeWaitingSightings(): Flow<List<QueuedSighting>>

    @Query("UPDATE photos SET problem = NULL, problemMessage = NULL WHERE id = :id")
    suspend fun retryPhoto(id: String)

    @Query("UPDATE sightings SET problem = NULL WHERE id = :id")
    suspend fun retrySighting(id: String)

    @Query("DELETE FROM photos WHERE id = :id")
    suspend fun deletePhoto(id: String)

    @Query("DELETE FROM sightings WHERE id = :id")
    suspend fun deleteSighting(id: String)

    @Query("DELETE FROM photos WHERE sentAt < :before")
    suspend fun forgetPhotosSentBefore(before: Long)

    @Query("DELETE FROM sightings WHERE sentAt < :before")
    suspend fun forgetSightingsSentBefore(before: Long)
}
