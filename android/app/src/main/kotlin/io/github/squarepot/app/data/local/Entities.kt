// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data.local

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(tableName = "collections")
data class CollectionEntity(
    @PrimaryKey val id: String,
    val name: String,
    val plantCount: Int,
    /** When the server last read the sheet successfully, epoch millis; null before its first read. */
    val serverSyncedAt: Long?,
    /** Why the server's last read of the sheet failed, as the server words it. */
    val serverError: String?,
    /** The sheet's custom columns, in column order. */
    val customColumns: List<String>,
    /** Whether plants can be edited through the API (ADR 0006). */
    val editable: Boolean = false,
)

data class CollectionName(val id: String, val name: String)

data class CollectionColumns(val name: String, val customColumns: List<String>)

/** One plant. The tag index is not unique: two plants share a number while a collision is unresolved. */
@Entity(
    tableName = "plants",
    indices = [Index("tag"), Index("collectionId")],
)
data class PlantEntity(
    @PrimaryKey val id: String,
    val collectionId: String,
    val tag: String?,
    val sheetRow: Int,
    val fields: Map<String, String>,
    /** Values of the collection's custom columns by name. */
    val custom: Map<String, String>,
    /** Since when the plant has its status, YYYY-MM-DD; null without a status. */
    val statusSince: String? = null,
    /** When the plant was last seen, by a sighting or a photo, epoch millis; null when never seen. */
    val lastSeen: Long? = null,
    val photoCount: Int = 0,
    /** When the newest photo was taken, epoch millis; null without photos. */
    val lastPhoto: Long? = null,
    /** The photo to show for the plant. */
    val mainPhotoId: String? = null,
)

/** The single row describing the copy as a whole. */
@Entity(tableName = "sync_state")
data class SyncStateEntity(
    @PrimaryKey val id: Int = SINGLE_ROW,
    /** Cursor of the last applied sync; null before the first one. */
    val cursor: String? = null,
    /** `version` of the stored [schemaJson]. */
    val schemaVersion: Int? = null,
    /** The server's field schema, as JSON. */
    val schemaJson: String? = null,
    /** When the copy was last refreshed from the server, epoch millis. */
    val refreshedAt: Long? = null,
    /** When the last sync attempt ended, successful or not, epoch millis. */
    val attemptedAt: Long? = null,
    /** Why the last attempt failed ([io.github.squarepot.app.data.SyncFailure] name); null after a success. */
    val failure: String? = null,
) {
    companion object {
        const val SINGLE_ROW = 0
    }
}
