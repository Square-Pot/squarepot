// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data.local

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

/** Reads and writes the local copy. Many small queries, one per thing the sync and the screen need. */
@Suppress("TooManyFunctions")
@Dao
interface CopyDao {
    @Query("SELECT * FROM sync_state WHERE id = 0")
    suspend fun state(): SyncStateEntity?

    @Query("SELECT * FROM sync_state WHERE id = 0")
    fun observeState(): Flow<SyncStateEntity?>

    @Upsert
    suspend fun saveState(state: SyncStateEntity)

    @Query("SELECT * FROM collections ORDER BY name COLLATE NOCASE")
    fun observeCollections(): Flow<List<CollectionEntity>>

    @Query("SELECT id, name FROM collections")
    suspend fun collectionNames(): List<CollectionName>

    @Query("SELECT name, customColumns FROM collections ORDER BY name COLLATE NOCASE")
    fun observeCustomColumns(): Flow<List<CollectionColumns>>

    @Query("SELECT COUNT(*) FROM plants")
    fun observePlantCount(): Flow<Int>

    /** Every plant with [tag]: usually one, more while a number collision is unresolved. */
    @Query("SELECT * FROM plants WHERE tag = :tag ORDER BY collectionId, sheetRow")
    suspend fun plantsByTag(tag: String): List<PlantEntity>

    @Query("SELECT * FROM plants")
    suspend fun allPlants(): List<PlantEntity>

    @Upsert
    suspend fun upsertCollections(collections: List<CollectionEntity>)

    @Upsert
    suspend fun upsertPlants(plants: List<PlantEntity>)

    @Query("DELETE FROM collections WHERE id IN (:ids)")
    suspend fun deleteCollections(ids: List<String>)

    @Query("DELETE FROM plants WHERE id IN (:ids)")
    suspend fun deletePlants(ids: List<String>)

    @Query("DELETE FROM collections")
    suspend fun deleteAllCollections()

    @Query("DELETE FROM plants")
    suspend fun deleteAllPlants()
}
