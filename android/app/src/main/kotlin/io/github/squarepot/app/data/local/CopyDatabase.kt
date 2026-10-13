// SPDX-License-Identifier: Apache-2.0

package io.github.squarepot.app.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.TypeConverter
import androidx.room.TypeConverters
import io.github.squarepot.app.data.api.ApiJson
import kotlinx.serialization.builtins.MapSerializer
import kotlinx.serialization.builtins.serializer

/**
 * The phone's local copy of every collection (ADR 0005).
 *
 * The copy is a cache of the server. When an app update changes these tables, they are dropped
 * with the cursor, and the next sync downloads a full copy: no migrations, no exported schema.
 */
@Database(
    entities = [CollectionEntity::class, PlantEntity::class, SyncStateEntity::class],
    version = 1,
    exportSchema = false,
)
@TypeConverters(FieldsConverter::class)
abstract class CopyDatabase : RoomDatabase() {
    abstract fun copy(): CopyDao

    companion object {
        fun open(context: Context): CopyDatabase = Room
            .databaseBuilder(context, CopyDatabase::class.java, "copy.db")
            .fallbackToDestructiveMigration(dropAllTables = true)
            .build()
    }
}

/** Stores a plant's fields as one JSON object. */
class FieldsConverter {
    private val serializer = MapSerializer(String.serializer(), String.serializer())

    @TypeConverter
    fun toJson(fields: Map<String, String>): String = ApiJson.encodeToString(serializer, fields)

    @TypeConverter
    fun fromJson(json: String): Map<String, String> = ApiJson.decodeFromString(serializer, json)
}
